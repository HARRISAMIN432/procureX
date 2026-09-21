import asyncio
import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimitMiddleware:
    """Small single-instance sliding-window limiter for the free deployment profile."""

    def __init__(self, app: ASGIApp, *, requests: int = 120, window_seconds: int = 60) -> None:
        self.app = app
        self.requests = requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "").startswith("/health/"):
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        address = client[0] if client else "unknown"
        bucket = f"{address}:{scope.get('path', '')}"
        now = time.monotonic()
        async with self._lock:
            hits = self._hits[bucket]
            while hits and hits[0] <= now - self.window_seconds:
                hits.popleft()
            if len(hits) >= self.requests:
                retry_after = max(1, int(self.window_seconds - (now - hits[0])))
                response = JSONResponse(
                    status_code=429,
                    content={
                        "detail": {
                            "code": "rate_limit_exceeded",
                            "message": "Too many requests; retry later",
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )
                await response(scope, receive, send)
                return
            hits.append(now)
            if len(self._hits) > 10_000:
                self._hits = defaultdict(
                    deque,
                    {
                        key: value
                        for key, value in self._hits.items()
                        if value and value[-1] > now - self.window_seconds
                    },
                )
        await self.app(scope, receive, send)
