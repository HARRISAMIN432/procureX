import json
import logging
import re
import time
import uuid

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
logger = logging.getLogger("procurex.http")


def safe_request_id(headers: list[tuple[bytes, bytes]]) -> str:
    for name, raw_value in headers:
        if name.lower() != REQUEST_ID_HEADER:
            continue
        try:
            value = raw_value.decode("ascii")
        except UnicodeDecodeError:
            break
        if REQUEST_ID_PATTERN.fullmatch(value):
            return value
        break
    return str(uuid.uuid4())


class SecurityHeadersMiddleware:
    """Attach correlation and browser-hardening headers to every HTTP response."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool, slow_request_threshold_ms: int) -> None:
        self.app = app
        self.enable_hsts = enable_hsts
        self.slow_request_threshold_ms = slow_request_threshold_ms

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = safe_request_id(scope.get("headers", []))
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = time.perf_counter()
        response_started = False
        status_code = 500
        error_type: str | None = None

        async def send_with_security_headers(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                duration_ms = (time.perf_counter() - started_at) * 1000
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (REQUEST_ID_HEADER, request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                        (b"cache-control", b"no-store"),
                        (b"server-timing", f"app;dur={duration_ms:.1f}".encode("ascii")),
                    ]
                )
                if self.enable_hsts:
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_security_headers)
        except Exception as exc:
            error_type = type(exc).__name__
            if response_started:
                raise
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": {
                        "code": "internal_server_error",
                        "message": "Unexpected server error",
                        "request_id": request_id,
                    }
                },
            )
            await response(scope, receive, send_with_security_headers)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            route = scope.get("route")
            route_template = getattr(route, "path", None) or "<unmatched>"
            log_level = (
                logging.WARNING
                if status_code >= 500 or duration_ms >= self.slow_request_threshold_ms
                else logging.INFO
            )
            completion = {
                "event": "http_request_complete",
                "request_id": request_id,
                "http_method": scope.get("method"),
                "http_route": route_template,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
                "error_type": error_type,
            }
            logger.log(
                log_level,
                json.dumps(completion, sort_keys=True, separators=(",", ":")),
                extra=completion,
            )
