import io
from datetime import datetime, timezone
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
from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies.auth import get_current_user
from psychohelp.main import app
from psychohelp.repositories import news as repository
from psychohelp.routes.upload_limits import MAX_IMAGE_REQUEST_SIZE
from psychohelp.services import news_images, news
from psychohelp.schemas.news import NewsResponse


def photo(format="PNG", size=(8, 6), **kwargs):
    output = io.BytesIO()
    with Image.new("RGB", size, "red") as image:
        image.save(output, format, **kwargs)
    return output.getvalue()


@pytest.fixture
def news_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "NEWS_IMAGE_DIR", tmp_path / "photos")
    now = datetime.now(timezone.utc)
    news = SimpleNamespace(
        id=uuid4(), slug="news", image=None, date=now, event_date=now, type=None,
        title="Новость", description=None, link=None, text="Текст новости",
    )
    state = {news.id: news}

    async def get(news_id):
        return state.get(news_id)

    async def get_list(skip=0, take=100):
        return list(state.values())[skip:skip + take]

    async def update(news_id, data):
        current = state.get(news_id)
        if current is None:
            return None, None
        previous_image = current.image
        changed = SimpleNamespace(**(vars(current) | data))
        state[news_id] = changed
        return changed, previous_image

    async def delete(news_id):
        current = state.pop(news_id, None)
        return (False, None) if current is None else (True, current.image)

    monkeypatch.setattr(repository, "get_news_by_id", get)
    monkeypatch.setattr(repository, "get_news_list", get_list)
    monkeypatch.setattr(repository, "update_news_with_previous_image", update)
    monkeypatch.setattr(repository, "delete_news_with_previous_image", delete)
    return news, state


@pytest.fixture
async def client(news_state):
    async def current_user():
        return SimpleNamespace(id=uuid4(), roles=[SimpleNamespace(code=RoleCode.ADMIN)])

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


async def upload(client, news_id, contents=None, content_type="image/png", filename="photo.png"):
    return await client.post(
        f"/news/{news_id}/image",
        files={"image": (filename, photo() if contents is None else contents, content_type)},
    )


def stored_files():
    return list(config.NEWS_IMAGE_DIR.iterdir()) if config.NEWS_IMAGE_DIR.exists() else []


async def test_photo_lifecycle_through_http(client, news_state):
    news, state = news_state
    original = NewsResponse.model_validate(news).model_dump(mode="json")
    response = await upload(client, news.id, filename="../../unsafe.php.png")
    assert response.status_code == 200, response.text
    first_url = response.json()["image"]
    assert news_images.IMAGE_FILENAME.fullmatch(first_url.rsplit("/", 1)[1])
    assert response.json() | {"image": None} == {**original, "id": str(news.id)}
    public = await client.get(first_url)
    assert public.status_code == 200
    assert public.headers["content-type"] == "image/webp"
    assert public.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(public.content)) as image:
        assert image.format == "WEBP"
        assert image.size == (8, 6)
    assert (await client.get(f"/news/{news.id}")).json()["image"] == first_url
    assert (await client.get("/news/")).json()[0]["image"] == first_url

    changed = await client.put(f"/news/{news.id}", json={"title": "Новый заголовок"})
    assert changed.json()["image"] == first_url
    replaced = await upload(client, news.id, photo("JPEG"), "image/jpeg")
    assert replaced.status_code == 200
    second_url = replaced.json()["image"]
    assert second_url != first_url
    assert (await client.get(first_url)).status_code == 404
    assert len(stored_files()) == 1

    # Существующие клиенты JSON API по-прежнему могут удалить фотографию
    cleared = await client.put(f"/news/{news.id}", json={"image": None})
    assert cleared.status_code == 200
    assert cleared.json()["image"] is None
    assert not stored_files()
    for _ in range(2):
        cleared = await client.delete(f"/news/{news.id}/image")
        assert cleared.status_code == 200
        assert cleared.json()["image"] is None
    assert (await upload(client, news.id)).status_code == 200
    cleared = await client.delete(f"/news/{news.id}/image")
    assert cleared.status_code == 200
    assert not stored_files()
    assert (await upload(client, news.id)).status_code == 200
    deleted = await client.delete(f"/news/{news.id}")
    assert deleted.status_code == 200
    assert news.id not in state
    assert not stored_files()


@pytest.mark.parametrize("format,mime,filename", [
    ("JPEG", "image/jpeg", "photo.jpg"),
    ("JPEG", "image/jpeg", "photo.jpeg"),
    ("PNG", "image/png", "photo.png"),
    ("WEBP", "image/webp", "photo.webp"),
])
async def test_supported_formats_are_decoded_and_reencoded(client, news_state, format, mime, filename):
    response = await upload(client, news_state[0].id, photo(format), mime, filename)
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
    (b"x" * (news_images.MAX_IMAGE_SIZE + 1), "image/png", 413),
], ids=["empty", "script", "svg", "gif", "bmp", "wrong-mime", "binary", "corrupt", "oversized"])
async def test_invalid_upload_preserves_current_image(client, news_state, contents, mime, status):
    news = news_state[0]
    first = (await upload(client, news.id)).json()["image"]
    response = await upload(client, news.id, contents, mime)
    assert response.status_code == status, response.text
    assert news_state[1][news.id].image == first
    assert (await client.get(first)).status_code == 200
    assert len(stored_files()) == 1


async def test_animation_is_rejected(client, news_state):
    with Image.new("RGB", (8, 6), "blue") as second:
        animated = photo(save_all=True, append_images=[second], duration=100, loop=0)
    response = await upload(client, news_state[0].id, animated)
    assert response.status_code == 400
    assert not stored_files()


async def test_resolution_limits_are_enforced_before_pixel_decode(client, news_state, monkeypatch):
    monkeypatch.setattr(news_images, "MAX_IMAGE_PIXELS", 48)
    assert (await upload(client, news_state[0].id, photo(size=(8, 6)))).status_code == 200
    assert (await upload(client, news_state[0].id, photo(size=(9, 6)))).status_code == 400
    monkeypatch.setattr(news_images, "MAX_IMAGE_DIMENSION", 10)
    assert (await upload(client, news_state[0].id, photo(size=(11, 1)))).status_code == 400


async def test_decompression_bomb_is_rejected(client, news_state, monkeypatch):
    contents = photo()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 20)
    response = await upload(client, news_state[0].id, contents)
    assert response.status_code == 400
    assert not stored_files()


async def test_exif_orientation_is_applied_and_metadata_is_removed(client, news_state):
    exif = Image.Exif()
    exif[274] = 6  # Поворот на 90 градусов по часовой стрелке
    exif[315] = "Private author"
    contents = photo("JPEG", exif=exif) + b"<script>discard appended content</script>"
    response = await upload(client, news_state[0].id, contents, "image/jpeg")
    assert response.status_code == 200, response.text
    public = await client.get(response.json()["image"])
    assert b"Private author" not in public.content
    assert b"<script>" not in public.content
    with Image.open(io.BytesIO(public.content)) as image:
        assert image.size == (6, 8)
        assert not image.getexif()


@pytest.mark.parametrize("method", ["post", "delete"])
@pytest.mark.parametrize("authenticated,status", [(False, 401), (True, 403)])
async def test_photo_changes_require_authentication_and_admin_role(
    client, news_state, method, authenticated, status,
):
    if not authenticated:
        app.dependency_overrides.pop(get_current_user)
    else:
        async def non_admin():
            return SimpleNamespace(id=uuid4(), roles=[SimpleNamespace(code=RoleCode.USER)])
        app.dependency_overrides[get_current_user] = non_admin
    if method == "post":
        response = await upload(client, news_state[0].id)
    else:
        response = await client.delete(f"/news/{news_state[0].id}/image")
    assert response.status_code == status, response.text
    assert not stored_files()


async def test_missing_news_and_invalid_requests(client):
    missing = uuid4()
    assert (await upload(client, missing)).status_code == 404
    assert (await client.delete(f"/news/{missing}/image")).status_code == 404
    assert (await upload(client, "not-a-uuid")).status_code == 422
    assert (await client.post(f"/news/{missing}/image")).status_code == 422
    assert not stored_files()


async def test_database_error_rolls_back_new_file(client, news_state, monkeypatch):
    news = news_state[0]
    old_url = (await upload(client, news.id)).json()["image"]
    monkeypatch.setattr(repository, "update_news_with_previous_image", AsyncMock(side_effect=SQLAlchemyError("DB unavailable")))
    response = await upload(client, news.id)
    assert response.status_code == 500
    assert response.json() == {"detail": "Не удалось сохранить фотографию"}
    assert news_state[1][news.id].image == old_url
    assert (await client.get(old_url)).status_code == 200
    assert len(stored_files()) == 1


async def test_photo_exactly_at_size_limit_is_accepted(client, news_state):
    contents = photo()
    contents += b"x" * (news_images.MAX_IMAGE_SIZE - len(contents))
    response = await upload(client, news_state[0].id, contents)
    assert response.status_code == 200, response.text
    assert stored_files()[0].stat().st_size < 1024


async def test_cleanup_failure_does_not_undo_committed_replacement(client, news_state, monkeypatch):
    from pathlib import Path

    news_id = news_state[0].id
    old_url = (await upload(client, news_id)).json()["image"]
    old_name = old_url.rsplit("/", 1)[1]
    original_unlink = Path.unlink

    def denied_unlink(path, *args, **kwargs):
        if path.name == old_name:
            raise PermissionError("File cannot be removed")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied_unlink)
    response = await upload(client, news_id)
    assert response.status_code == 200, response.text
    assert response.json()["image"] != old_url
    assert news_state[1][news_id].image == response.json()["image"]
    assert (await client.get(response.json()["image"])).status_code == 200


async def test_deleted_during_upload_does_not_leave_file(client, news_state, monkeypatch):
    monkeypatch.setattr(repository, "update_news_with_previous_image", AsyncMock(return_value=(None, None)))
    response = await upload(client, news_state[0].id)
    assert response.status_code == 404
    assert not stored_files()


async def test_storage_failure_preserves_photo_and_removes_temporary_file(client, news_state, monkeypatch):
    news = news_state[0]
    old_url = (await upload(client, news.id)).json()["image"]
    contents = photo()

    def fail_save(self, fp, *args, **kwargs):
        fp.write(b"partial write")
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", fail_save)
    response = await upload(client, news.id, contents)
    assert response.status_code == 500
    assert response.json()["detail"] == "Не удалось сохранить фотографию"
    assert news_state[1][news.id].image == old_url
    assert len(stored_files()) == 1
    assert (await client.get(old_url)).status_code == 200


async def test_file_read_is_bounded_and_upload_is_closed(news_state):
    upload_file = UploadFile(io.BytesIO(b"x" * (news_images.MAX_IMAGE_SIZE + 2)), headers=Headers({"content-type": "image/png"}))
    upload_file.read = AsyncMock(wraps=upload_file.read)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await news.upload_news_image(news_state[0].id, upload_file)
    assert error.value.status_code == 413
    upload_file.read.assert_awaited_once_with(news_images.MAX_IMAGE_SIZE + 1)
    assert upload_file.file.closed


def test_cleanup_cannot_delete_foreign_or_arbitrary_files(news_state, tmp_path):
    news = news_state[0]
    foreign_id = uuid4()
    config.NEWS_IMAGE_DIR.mkdir()
    foreign = config.NEWS_IMAGE_DIR / f"{foreign_id.hex}_{uuid4().hex}.webp"
    foreign.write_bytes(b"foreign photo")
    outside = tmp_path / "outside.webp"
    outside.write_bytes(b"private data")
    for url in [
        f"/media/news/{foreign.name}", "/media/news/../outside.webp",
        "/media/news/../../outside.webp", str(outside),
        "https://example.org/photo.webp", "/image/legacy.jpg", None,
    ]:
        news_images.remove_news_image(news.id, url)
    assert foreign.read_bytes() == b"foreign photo"
    assert outside.read_bytes() == b"private data"


async def test_public_route_rejects_symlinks_and_non_generated_filenames(client, news_state, tmp_path):
    config.NEWS_IMAGE_DIR.mkdir()
    private = tmp_path / "private.webp"
    private.write_bytes(b"private data")
    filename = f"{news_state[0].id.hex}_{uuid4().hex}.webp"
    (config.NEWS_IMAGE_DIR / filename).symlink_to(private)
    for name in [filename, "photo.webp", "../private.webp", "%2e%2e%5cprivate.webp", "partial.tmp", "bad%00.webp"]:
        response = await client.get(f"/media/news/{name}")
        assert response.status_code == 404, response.text


async def test_photo_urls_work_behind_api_prefix(client, news_state):
    news_id = news_state[0].id
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path="/api"), base_url="http://test/api",
    ) as prefixed:
        response = await upload(prefixed, news_id)
        assert response.status_code == 200, response.text
        url = response.json()["image"]
        assert url.startswith("/api/media/news/")
        assert (await prefixed.get("http://test" + url)).status_code == 200
        assert (await prefixed.get(f"/news/{news_id}")).json()["image"] == url
        assert (await prefixed.get("/news/")).json()[0]["image"] == url
        # Сохранение возвращённой ссылки не должно дублировать /api или мешать удалению файла новости.
        echoed = await prefixed.put(f"/news/{news_id}", json={"image": url})
        assert echoed.json()["image"] == url
        assert news_state[1][news_id].image == url.removeprefix("/api")
        assert len(stored_files()) == 1
        assert (await prefixed.delete(f"/news/{news_id}/image")).status_code == 200
        assert not stored_files()


@pytest.mark.parametrize("root_path", ["", "/api"])
@pytest.mark.parametrize("reference", ["absolute", "query", "absolute-query-fragment", "protocol-relative", "default-port"])
async def test_equivalent_photo_urls_preserve_file_and_allow_cleanup(client, news_state, root_path, reference):
    news_id = news_state[0].id
    suffix = "?v=1#preview" if "query" in reference else ""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path=root_path), base_url="http://test" + root_path,
    ) as api:
        uploaded = (await upload(api, news_id)).json()["image"]
        local_url = uploaded + suffix
        if reference.startswith("absolute"):
            image_url = "http://test" + local_url
        elif reference == "protocol-relative":
            image_url = "//test" + local_url
        elif reference == "default-port":
            image_url = "http://TEST:80" + local_url
        else:
            image_url = local_url

        changed = await api.put(f"/news/{news_id}", json={"image": image_url})
        assert changed.status_code == 200, changed.text
        assert changed.json()["image"] == local_url
        assert news_state[1][news_id].image == local_url.removeprefix(root_path)
        assert (await api.get("http://test" + local_url)).status_code == 200
        echoed = await api.put(f"/news/{news_id}", json={"image": changed.json()["image"]})
        assert echoed.json()["image"] == local_url
        assert (await api.get(f"/news/{news_id}")).json()["image"] == local_url
        assert len(stored_files()) == 1

        # Замена должна убрать прежний файл и после сохранения ссылки с query/fragment.
        replaced = await upload(api, news_id)
        assert replaced.status_code == 200, replaced.text
        assert (await api.get("http://test" + uploaded)).status_code == 404
        assert len(stored_files()) == 1
        current_url = replaced.json()["image"]
        changed = await api.put(f"/news/{news_id}", json={"image": "http://test" + current_url + "?v=2"})
        assert changed.status_code == 200, changed.text
        assert (await api.delete(f"/news/{news_id}/image")).status_code == 200
        assert not stored_files()
        assert (await api.get("http://test" + current_url)).status_code == 404


@pytest.mark.parametrize("origin", ["https://example.org", "//example.org", "https://test", "http://test:8000"])
async def test_external_photo_with_same_path_is_not_treated_as_local(client, news_state, origin):
    news_id = news_state[0].id
    uploaded = (await upload(client, news_id)).json()["image"]
    external = origin + uploaded + "?v=1#preview"
    changed = await client.put(f"/news/{news_id}", json={"image": external})
    assert changed.status_code == 200, changed.text
    assert changed.json()["image"] == external
    assert (await client.get(uploaded)).status_code == 404
    assert not stored_files()


@pytest.mark.parametrize("content_length,status", [
    (str(MAX_IMAGE_REQUEST_SIZE + 1), 413), ("-1", 400), ("invalid", 400),
    ("9" * 5000, 413),
])
async def test_request_length_is_checked_before_parsing(client, news_state, content_length, status):
    response = await client.post(
        f"/news/{news_state[0].id}/image",
        files={"image": ("photo.png", photo(), "image/png")},
        headers={"content-length": content_length},
    )
    assert response.status_code == status, response.text
    assert not stored_files()


@pytest.mark.parametrize("declared_length", [None, "1"])
async def test_streaming_request_limit_does_not_trust_content_length(client, news_state, declared_length):
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
    response = await client.post(f"/news/{news_state[0].id}/image", content=body(), headers=headers)
    assert response.status_code == 413, response.text
    assert sent_chunks < 20
    assert not stored_files()


def test_openapi_describes_upload_and_cookie_auth():
    operation = app.openapi()["paths"]["/news/{news_id}/image"]["post"]
    assert operation["security"] == [{"cookieAuth": []}]
    assert set(operation["responses"]) == {"200", "400", "401", "403", "404", "413", "415", "422", "500"}
    assert "multipart/form-data" in operation["requestBody"]["content"]


async def test_external_links_remain_compatible_and_replace_uploaded_files(client, news_state):
    news_id = news_state[0].id
    uploaded = (await upload(client, news_id)).json()["image"]
    external = "https://example.org/photo.jpg"
    changed = await client.put(f"/news/{news_id}", json={"image": external})
    assert changed.status_code == 200, changed.text
    assert changed.json()["image"] == external
    assert (await client.get(uploaded)).status_code == 404
    assert not stored_files()
    assert (await client.get(f"/news/{news_id}")).json()["image"] == external
    assert (await upload(client, news_id)).status_code == 200
    assert len(stored_files()) == 1
