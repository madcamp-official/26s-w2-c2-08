"""Tests for unauthenticated health endpoints."""

from fastapi.testclient import TestClient

from tbd.main import app


def test_health_returns_ok() -> None:
    """The liveness endpoint must not require a running database."""

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
