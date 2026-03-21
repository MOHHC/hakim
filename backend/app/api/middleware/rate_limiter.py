"""Per-IP sliding-window rate limiter middleware."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class _SlidingWindowLimiter:
    """Thread-safe in-memory sliding-window counter (per client IP)."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, ip: str) -> tuple[bool, int]:
        """Return ``(is_allowed, retry_after_seconds)``."""
        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets[ip]
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                retry_after = int(self._window - (now - bucket[0])) + 1
                return False, retry_after
            bucket.append(now)
            return True, 0

    def reset(self, ip: str | None = None) -> None:
        """Clear counters — used in tests."""
        if ip:
            self._buckets.pop(ip, None)
        else:
            self._buckets.clear()


# Module-level default limiter (10 req / 60 s)
default_limiter = _SlidingWindowLimiter(max_requests=10, window_seconds=60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests exceeding the per-IP limit with HTTP 429."""

    def __init__(self, app, limiter: _SlidingWindowLimiter | None = None) -> None:
        super().__init__(app)
        self._limiter = limiter or default_limiter

    async def dispatch(self, request: Request, call_next) -> Response:
        # Always allow CORS preflight through
        if request.method == "OPTIONS":
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        allowed, retry_after = await self._limiter.check(ip)
        if not allowed:
            return JSONResponse(
                {"detail": "Rate limit exceeded. Please try again later."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
