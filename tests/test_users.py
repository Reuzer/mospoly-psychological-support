from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from psychohelp.constants.rbac import PermissionCode, RoleCode
from psychohelp.dependencies.auth import get_optional_user
from psychohelp.main import app
from psychohelp.routes.controllers import users as users_controller


def _user(*role_codes):
    return SimpleNamespace(
        id=uuid4(),
        first_name="Иван",
        middle_name=None,
        last_name="Иванов",
        phone_number="+79991234567",
        email="user@example.com",
        social_media=None,
        study_group="231-001",
        roles=[
            SimpleNamespace(code=code, name=code.value, description=None)
            for code in role_codes
        ],
    )


async def _get_profile(monkeypatch, target, current_user, permissions=()):
    async def fake_get_user_by_id(user_id):
        return target if target is not None and user_id == target.id else None

    async def fake_has_permission(_user_id, permission_code):
        return permission_code in permissions

    async def fake_optional_user():
        return current_user

    monkeypatch.setattr(users_controller.users, "get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr(users_controller, "user_has_permission", fake_has_permission)
    app.dependency_overrides[get_optional_user] = fake_optional_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            target_id = target.id if target is not None else uuid4()
            return await client.get(f"/users/user/{target_id}")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_anonymous_cannot_get_user_profile(monkeypatch):
    response = await _get_profile(monkeypatch, _user(RoleCode.USER), None)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_other_user_without_permission_gets_403(monkeypatch):
    response = await _get_profile(
        monkeypatch, _user(RoleCode.USER), _user(RoleCode.USER)
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_gets_own_full_profile(monkeypatch):
    target = _user(RoleCode.USER)

    response = await _get_profile(monkeypatch, target, target)

    assert response.status_code == 200
    assert response.json()["email"] == target.email
    assert response.json()["study_group"] == target.study_group


@pytest.mark.asyncio
async def test_staff_with_permission_gets_full_profile(monkeypatch):
    target = _user(RoleCode.USER)

    response = await _get_profile(
        monkeypatch,
        target,
        _user(RoleCode.ADMIN),
        permissions={PermissionCode.USERS_VIEW_ALL},
    )

    assert response.status_code == 200
    assert response.json()["phone_number"] == target.phone_number


@pytest.mark.asyncio
@pytest.mark.parametrize("current_user", [None, _user(RoleCode.USER)])
async def test_psychologist_profile_is_public_card(monkeypatch, current_user):
    target = _user(RoleCode.PSYCHOLOGIST)

    response = await _get_profile(monkeypatch, target, current_user)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(target.id),
        "first_name": target.first_name,
        "middle_name": None,
        "last_name": target.last_name,
    }


@pytest.mark.asyncio
async def test_missing_user_returns_404(monkeypatch):
    response = await _get_profile(monkeypatch, None, _user(RoleCode.ADMIN))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_token_returns_401(monkeypatch):
    target = _user(RoleCode.USER)

    async def fake_get_user_by_id(user_id):
        return target if user_id == target.id else None

    monkeypatch.setattr(users_controller.users, "get_user_by_id", fake_get_user_by_id)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("access_token", "invalid-token")
        response = await client.get(f"/users/user/{target.id}")

    assert response.status_code == 401
