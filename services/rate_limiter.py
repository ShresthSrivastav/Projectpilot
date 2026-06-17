"""Rate limiter — in-memory token bucket per client IP."""
import logging
import os
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

LIMITS: dict[str, int] = {
    "generate": int(os.getenv("RATE_LIMIT_GENERATE", "5")),
    "benchmark": int(os.getenv("RATE_LIMIT_BENCHMARK", "10")),
    "evaluation": int(os.getenv("RATE_LIMIT_EVALUATION", "10")),
    "default": int(os.getenv("RATE_LIMIT_DEFAULT", "60")),
}

WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))


class TokenBucket:
    def __init__(self, capacity: int, window: int):
        self.capacity = capacity
        self.window = window
        self.tokens: dict[str, list[float]] = defaultdict(list)

    def consume(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        self.tokens[key] = [t for t in self.tokens[key] if t > cutoff]
        if len(self.tokens[key]) >= self.capacity:
            return False
        self.tokens[key].append(now)
        return True


buckets: dict[str, TokenBucket] = {
    name: TokenBucket(cap, WINDOW) for name, cap in LIMITS.items()
}


def _get_limit_key(request: Request) -> tuple[str, str]:
    client = request.client.host if request.client else "unknown"
    path = request.url.path

    if "/generate-project" in path or "/regenerate-file" in path or "/iterate/" in path:
        return client, "generate"
    if "/benchmark" in path or "/benchmarks" in path:
        return client, "benchmark"
    if "/evaluation" in path or "/evaluate" in path:
        return client, "evaluation"

    return client, "default"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not RATE_LIMIT_ENABLED:
            return await call_next(request)

        client, bucket_name = _get_limit_key(request)
        bucket = buckets.get(bucket_name, buckets["default"])

        if not bucket.consume(client):
            logger.warning("Rate limit exceeded for %s on %s (bucket=%s)", client, request.url.path, bucket_name)
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

        return await call_next(request)
