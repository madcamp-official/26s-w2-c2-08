"""Request correlation identifiers for HTTP responses and logs."""

import re
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")


def create_request_id() -> str:
    """Create an opaque server-side request correlation identifier."""

    return f"req_{uuid4().hex}"


def resolve_request_id(value: str | None) -> str:
    """Accept a safe client value or replace an absent or invalid value."""

    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return create_request_id()


def get_request_id(request: Request) -> str:
    """Read the request ID assigned by middleware, creating one as a fallback."""

    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = resolve_request_id(None)
        request.state.request_id = request_id
    return request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign one safe request ID and add it to every handled response."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
