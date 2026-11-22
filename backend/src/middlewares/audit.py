import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Ms"] = str(round((time.perf_counter() - started) * 1000, 2))
        return response
