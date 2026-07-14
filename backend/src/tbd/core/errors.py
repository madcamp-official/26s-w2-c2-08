"""Safe, contract-compatible HTTP error handling."""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from tbd.core.request_id import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An expected application failure with a stable public error code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details) if details is not None else None


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    """Build the shared error body without exposing implementation details."""

    request_id = get_request_id(request)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": dict(details) if details is not None else None,
            }
        },
        headers={REQUEST_ID_HEADER: request_id},
    )


def _validation_details(error: RequestValidationError) -> dict[str, list[dict[str, str]]]:
    """Expose only safe validation locations and stable Pydantic error types."""

    fields: list[dict[str, str]] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"] if part != "body")
        fields.append(
            {
                "field": location or "request",
                "reason": str(item["type"]),
            }
        )
    return {"fields": fields}


def _http_error_fields(status_code: int) -> tuple[str, str]:
    """Map framework-level HTTP failures to safe generic contract codes."""

    match status_code:
        case 400 | 405:
            return "INVALID_REQUEST", "요청 형식을 확인해 주세요."
        case 401:
            return "AUTHENTICATION_REQUIRED", "로그인이 필요합니다."
        case 403:
            return "COURSE_ACCESS_DENIED", "접근할 권한이 없습니다."
        case 404:
            return "RESOURCE_NOT_FOUND", "요청한 리소스를 찾을 수 없습니다."
        case 429:
            return "RATE_LIMITED", "요청 횟수가 너무 많습니다. 잠시 후 다시 시도해 주세요."
        case _:
            return "INVALID_REQUEST", "요청을 처리할 수 없습니다."


def install_exception_handlers(app: FastAPI) -> None:
    """Install the shared error envelope for all HTTP failure paths."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        return error_response(
            request,
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            details=error.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="입력 형식을 확인해 주세요.",
            details=_validation_details(error),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        code, message = _http_error_fields(error.status_code)
        return error_response(
            request,
            status_code=error.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        logger.exception("Unhandled HTTP request failure", extra={"request_id": request_id})
        return error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="요청 처리 중 오류가 발생했습니다.",
        )
