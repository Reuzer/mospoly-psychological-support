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
from psychohelp.models import psy_tests as psy_test_models
from psychohelp.repositories import psy_tests as repository
from psychohelp.routes.upload_limits import MAX_PSY_TEST_IMAGE_REQUEST_SIZE as MAX_IMAGE_REQUEST_SIZE
from psychohelp.services import psy_test_images, psy_tests
from psychohelp.services.rbac import permissions


def photo(format="PNG", size=(8, 6), **kwargs):
    output = io.BytesIO()
    with Image.new("RGB", size, "red") as image:
        image.save(output, format, **kwargs)
    return output.getvalue()


@pytest.fixture
def psy_test_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PSY_TEST_IMAGE_DIR", tmp_path / "photos")
    psy_test = SimpleNamespace(
        id=uuid4(), title="Тест", description="Описание теста", image=None,
        type=psy_test_models.TestType.MEDICAL.value, created_at="2026-11-08T00:00:00Z",
    )
    state = {psy_test.id: psy_test}

    async def get(psy_test_id):
        return state.get(psy_test_id)

    async def get_list(skip=0, take=100):
        return list(state.values())[skip:skip + take]

    async def update(psy_test_id, data):
        current = state.get(psy_test_id)
        if current is None:
            return None, None
        previous_image = current.image
        changed = SimpleNamespace(**(vars(current) | data))
        state[psy_test_id] = changed
        return changed, previous_image

    async def delete(psy_test_id):
        current = state.pop(psy_test_id, None)
        return (False, None) if current is None else (True, current.image)

    monkeypatch.setattr(repository, "get_psy_test_by_id", get)
    monkeypatch.setattr(repository, "get_psy_test_list", get_list)
    monkeypatch.setattr(repository, "update_psy_test_with_previous_image", update)
    monkeypatch.setattr(repository, "delete_psy_test_with_previous_image", delete)
    return psy_test, state


@pytest.fixture
async def client(monkeypatch, psy_test_state):
    async def current_user():
        return SimpleNamespace(id=uuid4())

    async def allowed(user_id, permission):
        assert permission in {PermissionCode.TESTS_EDIT, PermissionCode.TESTS_DELETE}
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


async def upload(client, psy_test_id, contents=None, content_type="image/png", filename="photo.png"):
    return await client.post(
        f"/psy-tests/{psy_test_id}/image",
        files={"image": (filename, photo() if contents is None else contents, content_type)},
    )


def stored_files():
    return list(config.PSY_TEST_IMAGE_DIR.iterdir()) if config.PSY_TEST_IMAGE_DIR.exists() else []


async def test_photo_lifecycle_through_http(client, psy_test_state):
    psy_test, state = psy_test_state
    original = vars(psy_test).copy()
    response = await upload(client, psy_test.id, filename="../../unsafe.php.png")
    assert response.status_code == 200, response.text
    first_url = response.json()["image"]
    assert psy_test_images.IMAGE_FILENAME.fullmatch(first_url.rsplit("/", 1)[1])
    assert response.json() | {"image": None} == {**original, "id": str(psy_test.id)}
    public = await client.get(first_url)
    assert public.status_code == 200
    assert public.headers["content-type"] == "image/webp"
    assert public.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(public.content)) as image:
        assert image.format == "WEBP"
        assert image.size == (8, 6)
    assert (await client.get(f"/psy-tests/{psy_test.id}")).json()["image"] == first_url
    assert (await client.get("/psy-tests/")).json()[0]["image"] == first_url

    changed = await client.put(f"/psy-tests/{psy_test.id}", json={"title": "Новый заголовок"})
    assert changed.json()["image"] == first_url
    replaced = await upload(client, psy_test.id, photo("JPEG"), "image/jpeg")
    assert replaced.status_code == 200
    second_url = replaced.json()["image"]
    assert second_url != first_url
    assert (await client.get(first_url)).status_code == 404
    assert len(stored_files()) == 1

    # Существующие клиенты JSON API по-прежнему могут удалить фотографию
    cleared = await client.put(f"/psy-tests/{psy_test.id}", json={"image": None})
    assert cleared.status_code == 200
    assert cleared.json()["image"] is None
    assert not stored_files()
    for _ in range(2):
        cleared = await client.delete(f"/psy-tests/{psy_test.id}/image")
        assert cleared.status_code == 200
        assert cleared.json()["image"] is None
    assert (await upload(client, psy_test.id)).status_code == 200
    cleared = await client.delete(f"/psy-tests/{psy_test.id}/image")
    assert cleared.status_code == 200
    assert not stored_files()
    assert (await upload(client, psy_test.id)).status_code == 200
    deleted = await client.delete(f"/psy-tests/{psy_test.id}")
    assert deleted.status_code == 200
    assert psy_test.id not in state
    assert not stored_files()


@pytest.mark.parametrize("format,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
async def test_supported_formats_are_decoded_and_reencoded(client, psy_test_state, format, mime):
    response = await upload(client, psy_test_state[0].id, photo(format), mime)
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
    (b"x" * (psy_test_images.MAX_IMAGE_SIZE + 1), "image/png", 413),
])
async def test_invalid_upload_preserves_current_image(client, psy_test_state, contents, mime, status):
    psy_test = psy_test_state[0]
    first = (await upload(client, psy_test.id)).json()["image"]
    response = await upload(client, psy_test.id, contents, mime)
    assert response.status_code == status, response.text
    assert psy_test_state[1][psy_test.id].image == first
    assert (await client.get(first)).status_code == 200
    assert len(stored_files()) == 1


async def test_animation_is_rejected(client, psy_test_state):
    with Image.new("RGB", (8, 6), "blue") as second:
        animated = photo(save_all=True, append_images=[second], duration=100, loop=0)
    response = await upload(client, psy_test_state[0].id, animated)
    assert response.status_code == 400
    assert not stored_files()


async def test_resolution_limits_are_enforced_before_pixel_decode(client, psy_test_state, monkeypatch):
    monkeypatch.setattr(psy_test_images, "MAX_IMAGE_PIXELS", 48)
    assert (await upload(client, psy_test_state[0].id, photo(size=(8, 6)))).status_code == 200
    assert (await upload(client, psy_test_state[0].id, photo(size=(9, 6)))).status_code == 400
    monkeypatch.setattr(psy_test_images, "MAX_IMAGE_DIMENSION", 10)
    assert (await upload(client, psy_test_state[0].id, photo(size=(11, 1)))).status_code == 400


async def test_decompression_bomb_is_rejected(client, psy_test_state, monkeypatch):
    contents = photo()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 20)
    response = await upload(client, psy_test_state[0].id, contents)
    assert response.status_code == 400
    assert not stored_files()


async def test_exif_orientation_is_applied_and_metadata_is_removed(client, psy_test_state):
    exif = Image.Exif()
    exif[274] = 6  # Поворот на 90 градусов по часовой стрелке
    exif[315] = "Private author"
    contents = photo("JPEG", exif=exif) + b"<script>discard appended content</script>"
    response = await upload(client, psy_test_state[0].id, contents, "image/jpeg")
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
    client, psy_test_state, monkeypatch, method, authenticated, status,
):
    if not authenticated:
        app.dependency_overrides.pop(get_current_user)
    denied = AsyncMock(return_value=False)
    monkeypatch.setattr(permissions, "user_has_permission", denied)
    if method == "post":
        response = await upload(client, psy_test_state[0].id)
    else:
        response = await client.delete(f"/psy-tests/{psy_test_state[0].id}/image")
    assert response.status_code == status, response.text
    if authenticated:
        assert denied.call_args.args[1] == PermissionCode.TESTS_EDIT
    assert not stored_files()


async def test_missing_psy_test_and_invalid_requests(client):
    missing = uuid4()
    assert (await upload(client, missing)).status_code == 404
    assert (await client.delete(f"/psy-tests/{missing}/image")).status_code == 404
    assert (await upload(client, "not-a-uuid")).status_code == 422
    assert (await client.post(f"/psy-tests/{missing}/image")).status_code == 422
    assert not stored_files()


async def test_database_error_rolls_back_new_file(client, psy_test_state, monkeypatch):
    psy_test = psy_test_state[0]
    old_url = (await upload(client, psy_test.id)).json()["image"]
    monkeypatch.setattr(repository, "update_psy_test_with_previous_image", AsyncMock(side_effect=SQLAlchemyError("DB unavailable")))
    response = await upload(client, psy_test.id)
    assert response.status_code == 500
    assert response.json() == {"detail": "Не удалось сохранить фотографию"}
    assert psy_test_state[1][psy_test.id].image == old_url
    assert (await client.get(old_url)).status_code == 200
    assert len(stored_files()) == 1


async def test_photo_exactly_at_size_limit_is_accepted(client, psy_test_state):
    contents = photo()
    contents += b"x" * (psy_test_images.MAX_IMAGE_SIZE - len(contents))
    response = await upload(client, psy_test_state[0].id, contents)
    assert response.status_code == 200, response.text
    assert stored_files()[0].stat().st_size < 1024


async def test_cleanup_failure_does_not_undo_committed_replacement(client, psy_test_state, monkeypatch):
    from pathlib import Path

    psy_test_id = psy_test_state[0].id
    old_url = (await upload(client, psy_test_id)).json()["image"]
    old_name = old_url.rsplit("/", 1)[1]
    original_unlink = Path.unlink

    def denied_unlink(path, *args, **kwargs):
        if path.name == old_name:
            raise PermissionError("File cannot be removed")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied_unlink)
    response = await upload(client, psy_test_id)
    assert response.status_code == 200, response.text
    assert response.json()["image"] != old_url
    assert psy_test_state[1][psy_test_id].image == response.json()["image"]
    assert (await client.get(response.json()["image"])).status_code == 200


async def test_deleted_during_upload_does_not_leave_file(client, psy_test_state, monkeypatch):
    monkeypatch.setattr(repository, "update_psy_test_with_previous_image", AsyncMock(return_value=(None, None)))
    response = await upload(client, psy_test_state[0].id)
    assert response.status_code == 404
    assert not stored_files()


async def test_storage_failure_preserves_photo_and_removes_temporary_file(client, psy_test_state, monkeypatch):
    psy_test = psy_test_state[0]
    old_url = (await upload(client, psy_test.id)).json()["image"]
    contents = photo()

    def fail_save(self, fp, *args, **kwargs):
        fp.write(b"partial write")
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", fail_save)
    response = await upload(client, psy_test.id, contents)
    assert response.status_code == 500
    assert response.json()["detail"] == "Не удалось сохранить фотографию"
    assert psy_test_state[1][psy_test.id].image == old_url
    assert len(stored_files()) == 1
    assert (await client.get(old_url)).status_code == 200


async def test_file_read_is_bounded_and_upload_is_closed(psy_test_state):
    upload_file = UploadFile(io.BytesIO(b"x" * (psy_test_images.MAX_IMAGE_SIZE + 2)), headers=Headers({"content-type": "image/png"}))
    upload_file.read = AsyncMock(wraps=upload_file.read)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await psy_tests.upload_psy_test_image(psy_test_state[0].id, upload_file)
    assert error.value.status_code == 413
    upload_file.read.assert_awaited_once_with(psy_test_images.MAX_IMAGE_SIZE + 1)
    assert upload_file.file.closed


def test_cleanup_cannot_delete_foreign_or_arbitrary_files(psy_test_state, tmp_path):
    psy_test = psy_test_state[0]
    foreign_id = uuid4()
    config.PSY_TEST_IMAGE_DIR.mkdir()
    foreign = config.PSY_TEST_IMAGE_DIR / f"{foreign_id.hex}_{uuid4().hex}.webp"
    foreign.write_bytes(b"foreign photo")
    outside = tmp_path / "outside.webp"
    outside.write_bytes(b"private data")
    for url in [
        f"/media/psy-tests/{foreign.name}", "/media/psy-tests/../outside.webp",
        "/media/psy-tests/../../outside.webp", str(outside),
        "https://example.org/photo.webp", "/image/legacy.jpg", None,
    ]:
        psy_test_images.remove_psy_test_image(psy_test.id, url)
    assert foreign.read_bytes() == b"foreign photo"
    assert outside.read_bytes() == b"private data"


async def test_public_route_rejects_symlinks_and_non_generated_filenames(client, psy_test_state, tmp_path):
    config.PSY_TEST_IMAGE_DIR.mkdir()
    private = tmp_path / "private.webp"
    private.write_bytes(b"private data")
    filename = f"{psy_test_state[0].id.hex}_{uuid4().hex}.webp"
    (config.PSY_TEST_IMAGE_DIR / filename).symlink_to(private)
    for name in [filename, "photo.webp", "../private.webp", "%2e%2e%5cprivate.webp", "partial.tmp", "bad%00.webp"]:
        response = await client.get(f"/media/psy-tests/{name}")
        assert response.status_code == 404, response.text


async def test_photo_urls_work_behind_api_prefix(client, psy_test_state):
    psy_test_id = psy_test_state[0].id
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path="/api"), base_url="http://test/api",
    ) as prefixed:
        response = await upload(prefixed, psy_test_id)
        assert response.status_code == 200, response.text
        url = response.json()["image"]
        assert url.startswith("/api/media/psy-tests/")
        assert (await prefixed.get("http://test" + url)).status_code == 200
        assert (await prefixed.get(f"/psy-tests/{psy_test_id}")).json()["image"] == url
        assert (await prefixed.get("/psy-tests/")).json()[0]["image"] == url
        # Сохранение возвращённой ссылки не должно дублировать /api или мешать удалению файла теста
        echoed = await prefixed.put(f"/psy-tests/{psy_test_id}", json={"image": url})
        assert echoed.json()["image"] == url
        assert psy_test_state[1][psy_test_id].image == url.removeprefix("/api")
        assert len(stored_files()) == 1
        assert (await prefixed.delete(f"/psy-tests/{psy_test_id}/image")).status_code == 200
        assert not stored_files()


@pytest.mark.parametrize("content_length,status", [
    (str(MAX_IMAGE_REQUEST_SIZE + 1), 413), ("-1", 400), ("invalid", 400),
    ("9" * 5000, 413),
])
async def test_request_length_is_checked_before_parsing(client, psy_test_state, content_length, status):
    response = await client.post(
        f"/psy-tests/{psy_test_state[0].id}/image",
        files={"image": ("photo.png", photo(), "image/png")},
        headers={"content-length": content_length},
    )
    assert response.status_code == status, response.text
    assert not stored_files()


@pytest.mark.parametrize("declared_length", [None, "1"])
async def test_streaming_request_limit_does_not_trust_content_length(client, psy_test_state, declared_length):
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
    response = await client.post(f"/psy-tests/{psy_test_state[0].id}/image", content=body(), headers=headers)
    assert response.status_code == 413, response.text
    assert sent_chunks < 20
    assert not stored_files()


def test_openapi_describes_upload_and_cookie_auth():
    operation = app.openapi()["paths"]["/psy-tests/{psy_test_id}/image"]["post"]
    assert operation["security"] == [{"cookieAuth": []}]
    assert set(operation["responses"]) == {"200", "400", "401", "403", "404", "413", "415", "422", "500"}
    assert "multipart/form-data" in operation["requestBody"]["content"]
