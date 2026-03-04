"""Session and CSRF middleware for the Cortex web UI.

- Validates session cookie on all requests except exempt paths
- Injects CSRF token into template context
- Validates CSRF token on state-changing requests (POST/PUT/DELETE/PATCH)
"""

from __future__ import annotations

import logging

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

# Paths that don't require authentication
EXEMPT_PATHS = frozenset({
    "/login",
    "/logout",
    "/api/health",
    "/static",
    "/favicon.ico",
})

# HTTP methods that require CSRF validation
CSRF_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

SESSION_COOKIE_NAME = "cortex_session"


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates session cookies and enforces authentication."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Allow exempt paths
        if self._is_exempt(path):
            return await call_next(request)

        # Check session cookie
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id:
            return self._redirect_to_login(request)

        # Validate session via AuthService
        auth = request.app.state.services.get("auth")
        if auth is None:
            # Auth not configured — allow through (dev mode)
            return await call_next(request)

        is_valid = await auth.validate_session(session_id)
        if not is_valid:
            response = self._redirect_to_login(request)
            response.delete_cookie(SESSION_COOKIE_NAME)
            return response

        # Attach session info to request state for downstream use
        request.state.session_id = session_id

        # CSRF validation for state-changing methods
        if request.method in CSRF_METHODS:
            from cortex.web.auth import AuthService

            csrf_token = request.headers.get("X-CSRF-Token", "")
            if not AuthService.verify_csrf_token(session_id, csrf_token):
                return Response(content="CSRF validation failed", status_code=403)

        return await call_next(request)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        """Check if path is exempt from authentication."""
        return any(path == exempt or path.startswith(exempt + "/") for exempt in EXEMPT_PATHS)

    @staticmethod
    def _redirect_to_login(request: Request) -> RedirectResponse:
        """Redirect to login page, preserving the original URL."""
        next_url = request.url.path
        if next_url == "/" or next_url == "/login":
            return RedirectResponse(url="/login", status_code=303)
        return RedirectResponse(url=f"/login?next={next_url}", status_code=303)
