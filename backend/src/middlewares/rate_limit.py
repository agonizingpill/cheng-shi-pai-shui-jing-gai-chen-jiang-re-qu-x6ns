import time
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit=120, window=60):
        super().__init__(app)
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api"):
            key = request.client.host if request.client else "local"
            now = time.time(); q = self.hits[key]
            while q and q[0] <= now - self.window: q.popleft()
            if len(q) >= self.limit:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "请求过于频繁，请稍后再试"}, status_code=429)
            q.append(now)
        return await call_next(request)
