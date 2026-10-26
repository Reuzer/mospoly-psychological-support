import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI

from psychohelp.config.config import config
from psychohelp.dependencies.auth import get_current_user
from psychohelp.main import app
from psychohelp.routes.controllers import applications
from psychohelp.schemas.errors import ErrorResponse
from psychohelp.services.applications.exceptions import (
    AccessDeniedError, ApplicationNotFoundError, ConflictError, ValidationError,
)


def test_exported_contract_matches_live_swagger():
    exported = json.loads((Path(__file__).resolve().parents[1] / "swagger.yaml").read_text())
    assert exported == app.openapi()


@pytest.mark.parametrize(("path", "codes"), [
    ("/applications/{application_id}/reassign", {"200", "400", "401", "403", "404", "409", "422"}),
    ("/applications/{application_id}/confirm", {"200", "400", "401", "403", "404", "409", "422"}),
    ("/appointments/{id}/reassign", {"200", "401", "403", "404", "409", "422"}),
])
def test_assignment_operations_document_actual_errors_and_cookie_auth(path, codes):
    operation = app.openapi()["paths"][path]["post"]
    assert set(operation["responses"]) == codes
    assert operation["security"] == [{"cookieAuth": []}]
    for code in codes - {"200", "422"}:
        assert operation["responses"][code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse",
        }
    assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError",
    }


def test_swagger_describes_created_message_and_binary_responses():
    paths = app.openapi()["paths"]
    assert set(paths["/users/register"]["post"]["responses"]) == {"201", "422"}
    for path in ("/appointments/create", "/appointments/{id}/reschedule-requests", "/therapists/{user_id}/statuses"):
        assert "201" in paths[path]["post"]["responses"]
        assert "200" not in paths[path]["post"]["responses"]
    for path, method in [("/users/logout", "post"), ("/appointments/{id}/cancel", "put"), ("/appointments/{id}/done", "put")]:
        schema = paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]
        model = app.openapi()["components"]["schemas"][schema["$ref"].split("/")[-1]]
        assert model["required"] == ["message"]
        assert model["properties"]["message"]["type"] == "string"
    assert "image/*" in paths["/image/{filename}"]["get"]["responses"]["200"]["content"]


@pytest.mark.parametrize("failure", ["invalid", "expired", "invalid_subject"])
async def test_bad_authentication_is_401_and_matches_documented_error(failure):
    if failure == "invalid":
        token = "invalid-token"
    else:
        token = jwt.encode(
            {"sub": "invalid-uuid" if failure == "invalid_subject" else str(uuid4()),
             "exp": datetime.now(timezone.utc) + timedelta(minutes=-1 if failure == "expired" else 5)},
            config.SECRET_KEY, algorithm=config.ALGORITHM,
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
        cookies={"access_token": token},
    ) as client:
        response = await client.post(f"/appointments/{uuid4()}/reassign")
    assert response.status_code == 401
    ErrorResponse.model_validate(response.json())


@pytest.mark.parametrize(("error", "status"), [
    (AccessDeniedError("Чужая заявка"), 403),
    (ApplicationNotFoundError(), 404),
    (ConflictError("Условия изменены"), 409),
    (ValidationError("Некорректные условия"), 400),
])
async def test_confirmation_http_errors_match_swagger(monkeypatch, error, status):
    test_app = FastAPI()
    test_app.include_router(applications.router)
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    confirm = AsyncMock(side_effect=error)
    monkeypatch.setattr(applications, "confirm_application", confirm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post(f"/applications/{uuid4()}/confirm", json={"expected_version": 3})
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert confirm.call_args.kwargs["expected_version"] == 3


@pytest.mark.parametrize("body", [{}, {"expected_version": 0}, {"expected_version": True}, {"expected_version": 3, "appointment_id": str(uuid4())}])
async def test_confirmation_requires_version_and_forbids_client_appointment_id(monkeypatch, body):
    test_app = FastAPI()
    test_app.include_router(applications.router)
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    confirm = AsyncMock()
    monkeypatch.setattr(applications, "confirm_application", confirm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post(f"/applications/{uuid4()}/confirm", json=body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    confirm.assert_not_awaited()


async def test_rate_limit_returns_documented_429_instead_of_internal_error(monkeypatch):
    from psychohelp.main import get_application
    from psychohelp.routes.controllers import users
    from psychohelp.schemas.errors import RateLimitErrorResponse
    from psychohelp.services.users.exceptions import WrongPassword

    monkeypatch.setattr(users.users, "login_user", AsyncMock(side_effect=WrongPassword()))
    users.limiter.reset()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=get_application()), base_url="http://test",
        ) as client:
            for _ in range(5):
                response = await client.post("/users/login", json={"email": "test@example.com", "password": "password123"})
                assert response.status_code == 401
            response = await client.post("/users/login", json={"email": "test@example.com", "password": "password123"})
        assert response.status_code == 429
        RateLimitErrorResponse.model_validate(response.json())
    finally:
        users.limiter.reset()
