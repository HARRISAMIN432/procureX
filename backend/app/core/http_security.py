import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


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

    def __init__(self, app: ASGIApp, *, enable_hsts: bool) -> None:
        self.app = app
        self.enable_hsts = enable_hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = safe_request_id(scope.get("headers", []))
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (REQUEST_ID_HEADER, request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                if self.enable_hsts:
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
