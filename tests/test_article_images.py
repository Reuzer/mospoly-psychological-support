import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import UploadFile
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers

from psychohelp.config.config import config
from psychohelp.constants.rbac import PermissionCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.main import app
from psychohelp.repositories import articles as repository
from psychohelp.routes.upload_limits import MAX_IMAGE_REQUEST_SIZE
from psychohelp.services import article_images, articles
from psychohelp.services.rbac import permissions


def photo(format="PNG", size=(8, 6), **kwargs):
    output = io.BytesIO()
    with Image.new("RGB", size, "red") as image:
        image.save(output, format, **kwargs)
    return output.getvalue()


@pytest.fixture
def article_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ARTICLE_IMAGE_DIR", tmp_path / "photos")
    article = SimpleNamespace(
        id=uuid4(), slug="article", image=None, date=None, author=None,
        title="Статья", description=None, text="Текст статьи",
    )
    state = {article.id: article}

    async def get(article_id):
        return state.get(article_id)

    async def get_list(skip=0, take=100):
        return list(state.values())[skip:skip + take]

    async def update(article_id, data):
        current = state.get(article_id)
        if current is None:
            return None, None
        previous_image = current.image
        changed = SimpleNamespace(**(vars(current) | data))
        state[article_id] = changed
        return changed, previous_image

    async def delete(article_id):
        current = state.pop(article_id, None)
        return (False, None) if current is None else (True, current.image)

    monkeypatch.setattr(repository, "get_article_by_id", get)
    monkeypatch.setattr(repository, "get_articles", get_list)
    monkeypatch.setattr(repository, "update_article_with_previous_image", update)
    monkeypatch.setattr(repository, "delete_article_with_previous_image", delete)
    return article, state


@pytest.fixture
async def client(monkeypatch, article_state):
    async def current_user():
        return SimpleNamespace(id=uuid4())

    async def allowed(user_id, permission):
        assert permission in {PermissionCode.ARTICLES_EDIT, PermissionCode.ARTICLES_DELETE}
        return True

    monkeypatch.setattr(permissions, "user_has_permission", allowed)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = current_user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def upload(client, article_id, contents=None, content_type="image/png", filename="photo.png"):
    return await client.post(
        f"/articles/{article_id}/image",
        files={"image": (filename, photo() if contents is None else contents, content_type)},
    )


def stored_files():
    return list(config.ARTICLE_IMAGE_DIR.iterdir()) if config.ARTICLE_IMAGE_DIR.exists() else []


async def test_photo_lifecycle_through_http(client, article_state):
    article, state = article_state
    original = vars(article).copy()
    response = await upload(client, article.id, filename="../../unsafe.php.png")
    assert response.status_code == 200, response.text
    first_url = response.json()["image"]
    assert article_images.IMAGE_FILENAME.fullmatch(first_url.rsplit("/", 1)[1])
    assert response.json() | {"image": None} == {**original, "id": str(article.id)}
    public = await client.get(first_url)
    assert public.status_code == 200
    assert public.headers["content-type"] == "image/webp"
    assert public.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(public.content)) as image:
        assert image.format == "WEBP"
        assert image.size == (8, 6)
    assert (await client.get(f"/articles/{article.id}")).json()["image"] == first_url
    assert (await client.get("/articles/")).json()[0]["image"] == first_url

    changed = await client.put(f"/articles/{article.id}", json={"title": "Новый заголовок"})
    assert changed.json()["image"] == first_url
    replaced = await upload(client, article.id, photo("JPEG"), "image/jpeg")
    assert replaced.status_code == 200
    second_url = replaced.json()["image"]
    assert second_url != first_url
    assert (await client.get(first_url)).status_code == 404
    assert len(stored_files()) == 1

    # Существующие клиенты JSON API по-прежнему могут удалить фотографию
    cleared = await client.put(f"/articles/{article.id}", json={"image": None})
    assert cleared.status_code == 200
    assert cleared.json()["image"] is None
    assert not stored_files()
    for _ in range(2):
        cleared = await client.delete(f"/articles/{article.id}/image")
        assert cleared.status_code == 200
        assert cleared.json()["image"] is None
    assert (await upload(client, article.id)).status_code == 200
    cleared = await client.delete(f"/articles/{article.id}/image")
    assert cleared.status_code == 200
    assert not stored_files()
    assert (await upload(client, article.id)).status_code == 200
    deleted = await client.delete(f"/articles/{article.id}")
    assert deleted.status_code == 200
    assert article.id not in state
    assert not stored_files()


@pytest.mark.parametrize("format,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
async def test_supported_formats_are_decoded_and_reencoded(client, article_state, format, mime):
    response = await upload(client, article_state[0].id, photo(format), mime)
    assert response.status_code == 200, response.text
    with Image.open(stored_files()[0]) as image:
        assert image.format == "WEBP"


@pytest.mark.parametrize("contents,mime,status", [
    (b"", "image/png", 400),
    (b"<script>alert(1)</script>", "image/png", 400),
    (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml", 415),
    (photo("GIF"), "image/png", 415),
    (photo("BMP"), "image/png", 415),
    (photo(), "image/jpeg", 400),
    (photo(), "application/octet-stream", 415),
    (photo()[:40], "image/png", 400),
    (b"x" * (article_images.MAX_IMAGE_SIZE + 1), "image/png", 413),
])
async def test_invalid_upload_preserves_current_image(client, article_state, contents, mime, status):
    article = article_state[0]
    first = (await upload(client, article.id)).json()["image"]
    response = await upload(client, article.id, contents, mime)
    assert response.status_code == status, response.text
    assert article_state[1][article.id].image == first
    assert (await client.get(first)).status_code == 200
    assert len(stored_files()) == 1


async def test_animation_is_rejected(client, article_state):
    with Image.new("RGB", (8, 6), "blue") as second:
        animated = photo(save_all=True, append_images=[second], duration=100, loop=0)
    response = await upload(client, article_state[0].id, animated)
    assert response.status_code == 400
    assert not stored_files()


async def test_resolution_limits_are_enforced_before_pixel_decode(client, article_state, monkeypatch):
    monkeypatch.setattr(article_images, "MAX_IMAGE_PIXELS", 48)
    assert (await upload(client, article_state[0].id, photo(size=(8, 6)))).status_code == 200
    assert (await upload(client, article_state[0].id, photo(size=(9, 6)))).status_code == 400
    monkeypatch.setattr(article_images, "MAX_IMAGE_DIMENSION", 10)
    assert (await upload(client, article_state[0].id, photo(size=(11, 1)))).status_code == 400


async def test_decompression_bomb_is_rejected(client, article_state, monkeypatch):
    contents = photo()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 20)
    response = await upload(client, article_state[0].id, contents)
    assert response.status_code == 400
    assert not stored_files()


async def test_exif_orientation_is_applied_and_metadata_is_removed(client, article_state):
    exif = Image.Exif()
    exif[274] = 6  # Поворот на 90 градусов по часовой стрелке
    exif[315] = "Private author"
    contents = photo("JPEG", exif=exif) + b"<script>discard appended content</script>"
    response = await upload(client, article_state[0].id, contents, "image/jpeg")
    assert response.status_code == 200, response.text
    public = await client.get(response.json()["image"])
    assert b"Private author" not in public.content
    assert b"<script>" not in public.content
    with Image.open(io.BytesIO(public.content)) as image:
        assert image.size == (6, 8)
        assert not image.getexif()


@pytest.mark.parametrize("method", ["post", "delete"])
@pytest.mark.parametrize("authenticated,status", [(False, 401), (True, 403)])
async def test_photo_changes_require_authentication_and_edit_permission(
    client, article_state, monkeypatch, method, authenticated, status,
):
    if not authenticated:
        app.dependency_overrides.pop(get_current_user)
    denied = AsyncMock(return_value=False)
    monkeypatch.setattr(permissions, "user_has_permission", denied)
    if method == "post":
        response = await upload(client, article_state[0].id)
    else:
        response = await client.delete(f"/articles/{article_state[0].id}/image")
    assert response.status_code == status, response.text
    if authenticated:
        assert denied.call_args.args[1] == PermissionCode.ARTICLES_EDIT
    assert not stored_files()


async def test_missing_article_and_invalid_requests(client):
    missing = uuid4()
    assert (await upload(client, missing)).status_code == 404
    assert (await client.delete(f"/articles/{missing}/image")).status_code == 404
    assert (await upload(client, "not-a-uuid")).status_code == 422
    assert (await client.post(f"/articles/{missing}/image")).status_code == 422
    assert not stored_files()


async def test_database_error_rolls_back_new_file(client, article_state, monkeypatch):
    article = article_state[0]
    old_url = (await upload(client, article.id)).json()["image"]
    monkeypatch.setattr(repository, "update_article_with_previous_image", AsyncMock(side_effect=SQLAlchemyError("DB unavailable")))
    response = await upload(client, article.id)
    assert response.status_code == 500
    assert response.json() == {"detail": "Не удалось сохранить фотографию"}
    assert article_state[1][article.id].image == old_url
    assert (await client.get(old_url)).status_code == 200
    assert len(stored_files()) == 1


async def test_photo_exactly_at_size_limit_is_accepted(client, article_state):
    contents = photo()
    contents += b"x" * (article_images.MAX_IMAGE_SIZE - len(contents))
    response = await upload(client, article_state[0].id, contents)
    assert response.status_code == 200, response.text
    assert stored_files()[0].stat().st_size < 1024


async def test_cleanup_failure_does_not_undo_committed_replacement(client, article_state, monkeypatch):
    from pathlib import Path

    article_id = article_state[0].id
    old_url = (await upload(client, article_id)).json()["image"]
    old_name = old_url.rsplit("/", 1)[1]
    original_unlink = Path.unlink

    def denied_unlink(path, *args, **kwargs):
        if path.name == old_name:
            raise PermissionError("File cannot be removed")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied_unlink)
    response = await upload(client, article_id)
    assert response.status_code == 200, response.text
    assert response.json()["image"] != old_url
    assert article_state[1][article_id].image == response.json()["image"]
    assert (await client.get(response.json()["image"])).status_code == 200


async def test_deleted_during_upload_does_not_leave_file(client, article_state, monkeypatch):
    monkeypatch.setattr(repository, "update_article_with_previous_image", AsyncMock(return_value=(None, None)))
    response = await upload(client, article_state[0].id)
    assert response.status_code == 404
    assert not stored_files()


async def test_storage_failure_preserves_photo_and_removes_temporary_file(client, article_state, monkeypatch):
    article = article_state[0]
    old_url = (await upload(client, article.id)).json()["image"]
    contents = photo()

    def fail_save(self, fp, *args, **kwargs):
        fp.write(b"partial write")
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", fail_save)
    response = await upload(client, article.id, contents)
    assert response.status_code == 500
    assert response.json()["detail"] == "Не удалось сохранить фотографию"
    assert article_state[1][article.id].image == old_url
    assert len(stored_files()) == 1
    assert (await client.get(old_url)).status_code == 200


async def test_file_read_is_bounded_and_upload_is_closed(article_state):
    upload_file = UploadFile(io.BytesIO(b"x" * (article_images.MAX_IMAGE_SIZE + 2)), headers=Headers({"content-type": "image/png"}))
    upload_file.read = AsyncMock(wraps=upload_file.read)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await articles.upload_article_image(article_state[0].id, upload_file)
    assert error.value.status_code == 413
    upload_file.read.assert_awaited_once_with(article_images.MAX_IMAGE_SIZE + 1)
    assert upload_file.file.closed


def test_cleanup_cannot_delete_foreign_or_arbitrary_files(article_state, tmp_path):
    article = article_state[0]
    foreign_id = uuid4()
    config.ARTICLE_IMAGE_DIR.mkdir()
    foreign = config.ARTICLE_IMAGE_DIR / f"{foreign_id.hex}_{uuid4().hex}.webp"
    foreign.write_bytes(b"foreign photo")
    outside = tmp_path / "outside.webp"
    outside.write_bytes(b"private data")
    for url in [
        f"/media/articles/{foreign.name}", "/media/articles/../outside.webp",
        "/media/articles/../../outside.webp", str(outside),
        "https://example.org/photo.webp", "/image/legacy.jpg", None,
    ]:
        article_images.remove_article_image(article.id, url)
    assert foreign.read_bytes() == b"foreign photo"
    assert outside.read_bytes() == b"private data"


async def test_public_route_rejects_symlinks_and_non_generated_filenames(client, article_state, tmp_path):
    config.ARTICLE_IMAGE_DIR.mkdir()
    private = tmp_path / "private.webp"
    private.write_bytes(b"private data")
    filename = f"{article_state[0].id.hex}_{uuid4().hex}.webp"
    (config.ARTICLE_IMAGE_DIR / filename).symlink_to(private)
    for name in [filename, "photo.webp", "../private.webp", "%2e%2e%5cprivate.webp", "partial.tmp", "bad%00.webp"]:
        response = await client.get(f"/media/articles/{name}")
        assert response.status_code == 404, response.text


async def test_photo_urls_work_behind_api_prefix(client, article_state):
    article_id = article_state[0].id
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path="/api"), base_url="http://test/api",
    ) as prefixed:
        response = await upload(prefixed, article_id)
        assert response.status_code == 200, response.text
        url = response.json()["image"]
        assert url.startswith("/api/media/articles/")
        assert (await prefixed.get("http://test" + url)).status_code == 200
        assert (await prefixed.get(f"/articles/{article_id}")).json()["image"] == url
        assert (await prefixed.get("/articles/")).json()[0]["image"] == url
        # Сохранение возвращённой ссылки не должно дублировать /api или мешать удалению файла статьи
        echoed = await prefixed.put(f"/articles/{article_id}", json={"image": url})
        assert echoed.json()["image"] == url
        assert article_state[1][article_id].image == url.removeprefix("/api")
        assert len(stored_files()) == 1
        assert (await prefixed.delete(f"/articles/{article_id}/image")).status_code == 200
        assert not stored_files()


@pytest.mark.parametrize("root_path", ["", "/api"])
@pytest.mark.parametrize("reference", ["absolute", "query", "absolute-query-fragment", "protocol-relative", "default-port"])
async def test_equivalent_photo_urls_preserve_file_and_allow_cleanup(client, article_state, root_path, reference):
    article_id = article_state[0].id
    suffix = "?v=1#preview" if "query" in reference else ""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path=root_path), base_url="http://test" + root_path,
    ) as api:
        uploaded = (await upload(api, article_id)).json()["image"]
        local_url = uploaded + suffix
        if reference.startswith("absolute"):
            image_url = "http://test" + local_url
        elif reference == "protocol-relative":
            image_url = "//test" + local_url
        elif reference == "default-port":
            image_url = "http://TEST:80" + local_url
        else:
            image_url = local_url

        changed = await api.put(f"/articles/{article_id}", json={"image": image_url})
        assert changed.status_code == 200, changed.text
        assert changed.json()["image"] == local_url
        assert article_state[1][article_id].image == local_url.removeprefix(root_path)
        assert (await api.get("http://test" + local_url)).status_code == 200
        echoed = await api.put(f"/articles/{article_id}", json={"image": changed.json()["image"]})
        assert echoed.json()["image"] == local_url
        assert (await api.get(f"/articles/{article_id}")).json()["image"] == local_url
        assert len(stored_files()) == 1

        replaced = await upload(api, article_id)
        assert replaced.status_code == 200, replaced.text
        assert (await api.get("http://test" + uploaded)).status_code == 404
        assert len(stored_files()) == 1
        current_url = replaced.json()["image"]
        changed = await api.put(f"/articles/{article_id}", json={"image": "http://test" + current_url + "?v=2"})
        assert changed.status_code == 200, changed.text
        assert (await api.delete(f"/articles/{article_id}/image")).status_code == 200
        assert not stored_files()
        assert (await api.get("http://test" + current_url)).status_code == 404


@pytest.mark.parametrize("origin", ["https://example.org", "//example.org", "https://test", "http://test:8000"])
async def test_external_photo_with_same_path_is_not_treated_as_local(client, article_state, origin):
    article_id = article_state[0].id
    uploaded = (await upload(client, article_id)).json()["image"]
    external = origin + uploaded + "?v=1#preview"
    changed = await client.put(f"/articles/{article_id}", json={"image": external})
    assert changed.status_code == 200, changed.text
    assert changed.json()["image"] == external
    assert (await client.get(uploaded)).status_code == 404
    assert not stored_files()


@pytest.mark.parametrize("content_length,status", [
    (str(MAX_IMAGE_REQUEST_SIZE + 1), 413), ("-1", 400), ("invalid", 400),
    ("9" * 5000, 413),
])
async def test_request_length_is_checked_before_parsing(client, article_state, content_length, status):
    response = await client.post(
        f"/articles/{article_state[0].id}/image",
        files={"image": ("photo.png", photo(), "image/png")},
        headers={"content-length": content_length},
    )
    assert response.status_code == status, response.text
    assert not stored_files()


@pytest.mark.parametrize("declared_length", [None, "1"])
async def test_streaming_request_limit_does_not_trust_content_length(client, article_state, declared_length):
    sent_chunks = 0

    async def body():
        nonlocal sent_chunks
        yield b'--boundary\r\nContent-Disposition: form-data; name="image"; filename="x.png"\r\nContent-Type: image/png\r\n\r\n'
        for _ in range(20):
            sent_chunks += 1
            yield b"x" * (1024 * 1024)
        yield b"\r\n--boundary--\r\n"

    headers = {"content-type": "multipart/form-data; boundary=boundary"}
    if declared_length:
        headers["content-length"] = declared_length
    response = await client.post(f"/articles/{article_state[0].id}/image", content=body(), headers=headers)
    assert response.status_code == 413, response.text
    assert sent_chunks < 20
    assert not stored_files()


def test_openapi_describes_upload_and_cookie_auth():
    operation = app.openapi()["paths"]["/articles/{article_id}/image"]["post"]
    assert operation["security"] == [{"cookieAuth": []}]
    assert set(operation["responses"]) == {"200", "400", "401", "403", "404", "413", "415", "422", "500"}
    assert "multipart/form-data" in operation["requestBody"]["content"]
