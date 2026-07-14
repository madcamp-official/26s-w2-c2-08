"""Tests for unauthenticated health endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_health_returns_ok(app: FastAPI) -> None:
    """The liveness endpoint must not require a running database."""

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"].startswith("req_")


def test_database_health_returns_ok(app: FastAPI) -> None:
    """The readiness endpoint can be tested without PostgreSQL through the fake."""

    with TestClient(app) as client:
        response = client.get("/api/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}
