"""Canonical OpenAPI checks for the currently implemented HTTP subset."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openapi_spec_validator import validate
from sqlalchemy.exc import SQLAlchemyError

pytestmark = [pytest.mark.unit, pytest.mark.contract]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPOSITORY_ROOT / "docs" / "api" / "openapi.yaml"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


@pytest.fixture(scope="module")
def canonical_openapi() -> dict[str, Any]:
    """Load and validate the complete canonical OpenAPI document."""

    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    validate(document)
    return document


def _resolve_local_refs(value: Any, document: dict[str, Any]) -> Any:
    """Resolve local OpenAPI references for JSON Schema payload validation."""

    if isinstance(value, list):
        return [_resolve_local_refs(item, document) for item in value]

    if not isinstance(value, dict):
        return value

    reference = value.get("$ref")
    if isinstance(reference, str):
        assert reference.startswith("#/"), f"external reference is not supported: {reference}"
        target: Any = document
        for token in reference[2:].split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
        resolved = _resolve_local_refs(deepcopy(target), document)
        siblings = {
            key: _resolve_local_refs(item, document) for key, item in value.items() if key != "$ref"
        }
        if siblings:
            assert isinstance(resolved, dict)
            resolved.update(siblings)
        return resolved

    return {key: _resolve_local_refs(item, document) for key, item in value.items()}


def _canonical_response(
    document: dict[str, Any],
    path: str,
    method: str,
    status_code: int,
) -> dict[str, Any]:
    response = document["paths"][path][method]["responses"][str(status_code)]
    resolved = _resolve_local_refs(response, document)
    assert isinstance(resolved, dict)
    return resolved


def _assert_response_matches_contract(
    response: Any,
    document: dict[str, Any],
    path: str,
    method: str,
) -> None:
    contract = _canonical_response(document, path, method, response.status_code)
    schema = contract["content"]["application/json"]["schema"]
    jsonschema.validate(response.json(), schema)
    assert "X-Request-ID" in contract["headers"]
    assert response.headers["X-Request-ID"]


def test_runtime_routes_are_a_subset_of_the_canonical_contract(
    app: FastAPI,
    canonical_openapi: dict[str, Any],
) -> None:
    """Implemented operations and responses must already exist in the contract.

    Canonical-but-unimplemented operations remain allowed until the full API
    comparison is intentionally enabled in PR-30.
    """

    runtime_paths = app.openapi()["paths"]
    canonical_paths = canonical_openapi["paths"]

    for path, runtime_path in runtime_paths.items():
        assert path in canonical_paths, f"implemented path is undocumented: {path}"
        for method, runtime_operation in runtime_path.items():
            if method not in HTTP_METHODS:
                continue
            assert method in canonical_paths[path], (
                f"implemented operation is undocumented: {method.upper()} {path}"
            )
            canonical_responses = canonical_paths[path][method]["responses"]
            for status_code in runtime_operation["responses"]:
                assert status_code in canonical_responses, (
                    f"implemented response is undocumented: {method.upper()} {path} {status_code}"
                )


def test_course_session_list_declares_cursor_contract(
    app: FastAPI,
    canonical_openapi: dict[str, Any],
) -> None:
    """Runtime and canonical schemas expose the bounded cursor and its 400 response."""

    path = "/api/v1/courses/{course_id}/sessions"
    canonical_operation = canonical_openapi["paths"][path]["get"]
    runtime_operation = app.openapi()["paths"][path]["get"]

    for operation in (canonical_operation, runtime_operation):
        parameters = {
            parameter["name"]: parameter
            for parameter in _resolve_local_refs(operation["parameters"], canonical_openapi)
        }
        assert {"status", "cursor", "limit"} <= parameters.keys()
        assert parameters["limit"]["schema"]["default"] == 20
        assert parameters["limit"]["schema"]["minimum"] == 1
        assert parameters["limit"]["schema"]["maximum"] == 100
        assert "400" in operation["responses"]

    response_schema = _resolve_local_refs(
        canonical_operation["responses"]["200"], canonical_openapi
    )["content"]["application/json"]["schema"]
    assert {"items", "next_cursor"} <= set(response_schema["required"])


@pytest.mark.parametrize("path", ["/api/health", "/api/health/db"])
def test_health_success_payloads_match_canonical_openapi(
    app: FastAPI,
    canonical_openapi: dict[str, Any],
    path: str,
) -> None:
    """The implemented health success bodies satisfy their canonical schemas."""

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 200
    _assert_response_matches_contract(response, canonical_openapi, path, "get")


def test_database_health_failure_matches_canonical_openapi(
    app: FastAPI,
    database: Any,
    canonical_openapi: dict[str, Any],
) -> None:
    """The implemented readiness error satisfies the canonical 503 schema."""

    database.failure = SQLAlchemyError("private provider detail")
    with TestClient(app) as client:
        response = client.get("/api/health/db")

    assert response.status_code == 503
    _assert_response_matches_contract(
        response,
        canonical_openapi,
        "/api/health/db",
        "get",
    )
