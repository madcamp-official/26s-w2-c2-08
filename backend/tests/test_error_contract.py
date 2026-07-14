"""Tests for the shared HTTP request ID and error contract."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from tbd.core.errors import ApiError


def test_valid_request_id_is_echoed(app: FastAPI) -> None:
    """A safe client correlation ID is returned unchanged."""

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"X-Request-ID": "client.trace-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "client.trace-1"


def test_invalid_request_id_is_replaced(app: FastAPI) -> None:
    """Unsafe request IDs cannot be reflected to response headers or logs."""

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"X-Request-ID": "invalid/request"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")


def test_database_failure_uses_safe_error_envelope(
    app: FastAPI,
    database: Any,
) -> None:
    """Database exception details must not escape through the readiness endpoint."""

    database.failure = SQLAlchemyError("postgres password must stay private")
    with TestClient(app) as client:
        response = client.get("/api/health/db", headers={"X-Request-ID": "trace-503"})

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "trace-503"
    assert response.json() == {
        "error": {
            "code": "DEPENDENCY_UNAVAILABLE",
            "message": "데이터베이스에 연결할 수 없습니다.",
            "request_id": "trace-503",
            "details": None,
        }
    }


def test_validation_error_uses_shared_envelope(app: FastAPI) -> None:
    """FastAPI validation failures expose safe locations, not raw submitted values."""

    @app.get("/_test/validation")
    async def validation_probe(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/_test/validation?value=not-an-integer")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    assert body["error"]["details"] == {
        "fields": [{"field": "query.value", "reason": "int_parsing"}]
    }
    assert "not-an-integer" not in str(body)


def test_application_error_and_unexpected_error_are_safe(app: FastAPI) -> None:
    """Expected and unexpected failures both retain the same correlation ID."""

    @app.get("/_test/application-error")
    async def application_error_probe() -> None:
        raise ApiError(
            status_code=409,
            code="TEST_CONFLICT",
            message="테스트 충돌입니다.",
            details={"resource": "test"},
        )

    @app.get("/_test/unexpected-error")
    async def unexpected_error_probe() -> None:
        raise RuntimeError("internal secret")

    with TestClient(app, raise_server_exceptions=False) as client:
        application_response = client.get("/_test/application-error")
        unexpected_response = client.get("/_test/unexpected-error")

    assert application_response.status_code == 409
    assert application_response.json()["error"]["code"] == "TEST_CONFLICT"
    assert unexpected_response.status_code == 500
    assert unexpected_response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "internal secret" not in unexpected_response.text
    assert (
        unexpected_response.json()["error"]["request_id"]
        == unexpected_response.headers["X-Request-ID"]
    )


def test_not_found_uses_shared_error_envelope(app: FastAPI) -> None:
    """Framework 404 responses use the same public body as application errors."""

    with TestClient(app) as client:
        response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_factory_lifespan_disposes_injected_database(
    app: FastAPI,
    database: Any,
) -> None:
    """The factory owns shutdown for the resource it receives."""

    with TestClient(app) as client:
        client.get("/api/health")

    assert database.dispose_calls == 1


def test_health_openapi_declares_request_id_and_error_response(app: FastAPI) -> None:
    """The implemented health subset advertises its shared headers and errors."""

    schema = app.openapi()
    health = schema["paths"]["/api/health"]["get"]
    database_health = schema["paths"]["/api/health/db"]["get"]

    assert "X-Request-ID" in health["responses"]["200"]["headers"]
    assert "X-Request-ID" in database_health["responses"]["503"]["headers"]
    assert database_health["responses"]["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
