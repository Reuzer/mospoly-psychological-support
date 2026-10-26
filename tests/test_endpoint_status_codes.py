from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from psychohelp.config.config import config
from psychohelp.constants.rbac import RoleCode
from psychohelp.dependencies import auth as auth_dependencies
from psychohelp.dependencies.auth import get_current_user
from psychohelp.main import app
from psychohelp.models.appointments import AppointmentStatus, AppointmentType
from psychohelp.routes.controllers import appointments as appointments_controller
from psychohelp.routes.controllers import users as users_controller
from psychohelp.services.rbac import permissions as permissions_service
from psychohelp.services.users import exceptions as users_exceptions


USER_ID = UUID("00000000-0000-0000-0000-000000000001")
RESOURCE_ID = "00000000-0000-0000-0000-000000000002"
FUTURE_TIME = "2030-01-01T10:00:00Z"


PROTECTED_ENDPOINTS = [
    ("GET", "/users/user", None),
    ("PUT", "/users/me", {}),
    ("PUT", f"/users/{RESOURCE_ID}", {}),
    (
        "POST",
        "/users/me/password",
        {"old_password": "oldpass12", "new_password": "newpass12"},
    ),
    ("GET", "/appointments/", None),
    (
        "POST",
        "/appointments/create",
        {
            "patient_id": str(USER_ID),
            "psychologist_id": RESOURCE_ID,
            "type": "Online",
            "scheduled_time": FUTURE_TIME,
            "venue": "https://example.com/meeting",
        },
    ),
    ("GET", f"/appointments/{RESOURCE_ID}", None),
    ("PUT", f"/appointments/{RESOURCE_ID}/cancel", {"cancel_reason": "Причина"}),
    ("GET", f"/appointments/{RESOURCE_ID}/reschedule-requests", None),
    (
        "POST",
        f"/appointments/{RESOURCE_ID}/reschedule-requests",
        {"scheduled_time": FUTURE_TIME},
    ),
    ("POST", f"/appointments/reschedule-requests/{RESOURCE_ID}/confirm", None),
    (
        "POST",
        f"/appointments/reschedule-requests/{RESOURCE_ID}/cancel",
        {"rejection_comment": "Не подходит время"},
    ),
    (
        "POST",
        f"/appointments/reschedule-requests/{RESOURCE_ID}/reject",
        {"rejection_comment": "Не подходит время"},
    ),
    ("PUT", f"/appointments/{RESOURCE_ID}/done", {}),
    ("POST", f"/roles/{RESOURCE_ID}/assign", {"role_code": "user"}),
    ("POST", f"/roles/{RESOURCE_ID}/remove", {"role_code": "user"}),
    (
        "POST",
        "/therapists/",
        {
            "user_id": RESOURCE_ID,
            "experience": "1 год",
            "qualification": "Психолог",
            "consult_areas": "Стресс",
            "description": "Описание",
            "office": "101",
            "education": "Высшее",
            "short_description": "Описание",
        },
    ),
    ("DELETE", f"/therapists/{RESOURCE_ID}", None),
    (
        "POST",
        "/applications/",
        {
            "psychologist_id": RESOURCE_ID,
            "scheduled_at": FUTURE_TIME,
            "problem_description": "Описание проблемы",
            "university_status": "студент",
        },
    ),
    ("GET", "/applications/", None),
    ("GET", f"/applications/{RESOURCE_ID}", None),
    ("POST", f"/applications/{RESOURCE_ID}/accept", {"assigned_to": RESOURCE_ID}),
    (
        "POST",
        f"/applications/{RESOURCE_ID}/offer",
        {
            "psychologist_id": RESOURCE_ID,
            "meeting_type": "online",
            "scheduled_at": FUTURE_TIME,
        },
    ),
    ("POST", f"/applications/{RESOURCE_ID}/confirm", None),
    ("POST", f"/applications/{RESOURCE_ID}/reject", {"reject_reason": "Причина"}),
    (
        "POST",
        f"/applications/{RESOURCE_ID}/cancel",
        {"cancel_reason": "Причина", "cancel_initiator": "user"},
    ),
    ("POST", "/articles/", {"slug": "article", "title": "Статья", "text": "Текст"}),
    ("PUT", f"/articles/{RESOURCE_ID}", {}),
    ("DELETE", f"/articles/{RESOURCE_ID}", None),
    ("POST", "/news/", {"slug": "news", "title": "Новость", "event_date": FUTURE_TIME}),
    ("PUT", f"/news/{RESOURCE_ID}", {}),
    ("DELETE", f"/news/{RESOURCE_ID}", None),
    (
        "POST",
        "/psy-tests/",
        {"title": "Тест", "description": "Описание", "type": "Медицинский"},
    ),
    ("PUT", f"/psy-tests/{RESOURCE_ID}", {}),
    ("DELETE", f"/psy-tests/{RESOURCE_ID}", None),
    (
        "POST",
        f"/therapists/{RESOURCE_ID}/statuses",
        {
            "status": "vacation",
            "start_date": "2030-01-01T00:00:00Z",
            "end_date": "2030-01-02T00:00:00Z",
        },
    ),
    ("DELETE", f"/therapists/{RESOURCE_ID}/statuses/{USER_ID}", None),
    ("GET", f"/therapists/{RESOURCE_ID}/statuses", None),
]


def _expired_token() -> str:
    return jwt.encode(
        {
            "sub": str(USER_ID),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        config.SECRET_KEY,
        algorithm=config.ALGORITHM,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", PROTECTED_ENDPOINTS)
@pytest.mark.parametrize("token", [None, "invalid-token", _expired_token()])
async def test_protected_endpoints_return_401_for_invalid_auth(
    method,
    path,
    payload,
    token,
):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        if token is not None:
            client.cookies.set("access_token", token)
        response = await client.request(method, path, json=payload)

    assert response.status_code == 401, (method, path, response.text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency",
    [auth_dependencies.get_current_user, auth_dependencies.get_optional_user],
)
async def test_auth_dependency_returns_401_when_token_user_is_missing(
    monkeypatch,
    dependency,
):
    async def fake_get_user_by_token(_token):
        return None

    monkeypatch.setattr(auth_dependencies, "get_user_by_token", fake_get_user_by_token)
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", b"access_token=valid-token")],
        }
    )

    with pytest.raises(HTTPException) as exc:
        await dependency(request)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_does_not_hide_database_errors(monkeypatch):
    async def fake_get_user_by_token(_token):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(auth_dependencies, "get_user_by_token", fake_get_user_by_token)
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", b"access_token=valid-token")],
        }
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await auth_dependencies.get_current_user(request)


@pytest.mark.asyncio
async def test_login_returns_401_for_invalid_credentials(monkeypatch):
    async def fake_login_user(_email, _password):
        raise users_exceptions.WrongPassword()

    monkeypatch.setattr(users_controller.users, "login_user", fake_login_user)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/users/login",
            json={"email": "user@example.com", "password": "incorrect"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, "invalid-token", _expired_token()])
async def test_refresh_returns_401_for_invalid_token(token):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        if token is not None:
            client.cookies.set("refresh_token", token)
        response = await client.post("/users/refresh")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("access_token", [None, "invalid-token", _expired_token()])
async def test_logout_clears_cookies_regardless_of_access_token(access_token):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        if access_token is not None:
            client.cookies.set("access_token", access_token)
        client.cookies.set("refresh_token", "valid-refresh-token")
        response = await client.post("/users/logout")

    set_cookie_headers = response.headers.get_list("set-cookie")

    access_cookie = next(
        header for header in set_cookie_headers if header.startswith("access_token=")
    )
    refresh_cookie = next(
        header for header in set_cookie_headers if header.startswith("refresh_token=")
    )

    assert response.status_code == 200
    assert "max-age=0" in access_cookie.lower()
    assert "max-age=0" in refresh_cookie.lower()


@pytest.mark.asyncio
async def test_authenticated_user_without_permission_gets_403(monkeypatch):
    current_user = SimpleNamespace(id=USER_ID, roles=[])

    async def fake_current_user():
        return current_user

    async def fake_has_permission(_user_id, _permission_code):
        return False

    app.dependency_overrides[get_current_user] = fake_current_user
    monkeypatch.setattr(permissions_service, "user_has_permission", fake_has_permission)
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/articles/",
                json={"slug": "article", "title": "Статья", "text": "Текст"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_appointment_returns_201(monkeypatch):
    current_user = SimpleNamespace(id=USER_ID, roles=[])
    now = datetime.now(timezone.utc)
    patient = SimpleNamespace(
        id=USER_ID,
        first_name="Иван",
        middle_name=None,
        last_name="Иванов",
        phone_number="+79991234567",
        email="student@example.com",
        social_media=None,
        study_group="231-001",
    )
    psychologist_user = SimpleNamespace(
        id=uuid4(),
        first_name="Анна",
        middle_name=None,
        last_name="Петрова",
        phone_number="+79997654321",
        email="psychologist@example.com",
        social_media=None,
        study_group=None,
    )
    psychologist = SimpleNamespace(
        id=uuid4(),
        user_id=psychologist_user.id,
        experience="5 лет",
        qualification="Психолог",
        consult_areas="Стресс",
        description="Описание",
        office="101",
        education="Высшее",
        short_description="Описание",
        photo=None,
        user=psychologist_user,
    )
    appointment = SimpleNamespace(
        id=uuid4(),
        patient=patient,
        psychologist=psychologist,
        application_id=None,
        type=AppointmentType.Online,
        reason=None,
        status=AppointmentStatus.awaiting,
        scheduled_time=now + timedelta(days=1),
        remind_time=None,
        last_change_time=now,
        venue="https://example.com/meeting",
        comment=None,
        cancel_reason=None,
        patient_comment=None,
        conclusion=None,
    )

    async def fake_current_user():
        return current_user

    async def fake_has_permission(_user_id, _permission_code):
        return True

    async def fake_create_appointment(**_kwargs):
        return appointment

    app.dependency_overrides[get_current_user] = fake_current_user
    monkeypatch.setattr(permissions_service, "user_has_permission", fake_has_permission)
    monkeypatch.setattr(
        appointments_controller,
        "srv_create_appointment",
        fake_create_appointment,
    )
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/appointments/create",
                json={
                    "patient_id": str(USER_ID),
                    "psychologist_id": str(psychologist.id),
                    "type": "Online",
                    "scheduled_time": (now + timedelta(days=1)).isoformat(),
                    "venue": "https://example.com/meeting",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_done_endpoint_requires_request_body():
    async def fake_current_user():
        return SimpleNamespace(id=USER_ID, roles=[])

    app.dependency_overrides[get_current_user] = fake_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(f"/appointments/{RESOURCE_ID}/done")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_openapi_declares_expected_success_status_codes():
    created_routes = {
        ("post", "/users/register"),
        ("post", "/appointments/create"),
        ("post", "/appointments/{id}/reschedule-requests"),
        ("post", "/therapists/"),
        ("post", "/therapists/{user_id}/statuses"),
        ("post", "/applications/"),
        ("post", "/articles/"),
        ("post", "/news/"),
        ("post", "/psy-tests/"),
    }
    schema = app.openapi()

    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            expected = "201" if (method, path) in created_routes else "200"
            assert expected in operation["responses"], (method, path, operation["responses"])
