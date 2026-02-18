"""
Security middleware: CSRF protection, security headers, org-scoping.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "connect-src 'self' wss://*.openclaw.dev; "
        "frame-ancestors 'none';"
    ),
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


# ---------------------------------------------------------------------------
# CSRF Protection (Double-Submit Cookie)
# ---------------------------------------------------------------------------

class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Double-submit cookie CSRF protection.

    Skipped for:
    - Safe HTTP methods (GET, HEAD, OPTIONS)
    - Requests with Authorization header (API key auth — not cookie-based)
    - Non-browser clients
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip for safe methods
        if request.method in SAFE_METHODS:
            return await call_next(request)

        # Skip for API key auth (agents don't use cookies)
        if request.headers.get("Authorization"):
            return await call_next(request)

        # Only enforce if there's a session cookie (browser request)
        if "mc_session" not in request.cookies:
            return await call_next(request)

        cookie_token = request.cookies.get("mc_csrf")
        header_token = request.headers.get("X-CSRF-Token")

        if not cookie_token or not header_token or cookie_token != header_token:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_VALIDATION_FAILED",
                        "message": "Invalid or missing CSRF token.",
                        "status": 403,
                    }
                },
            )

        return await call_next(request)
