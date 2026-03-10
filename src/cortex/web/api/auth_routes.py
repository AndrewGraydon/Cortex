"""Authentication routes — login/logout pages and form handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from cortex.security.rate_limiter import RateLimiter
from cortex.web.auth import AuthService
from cortex.web.middleware import SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Module-level rate limiter for login attempts
_login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=300.0)


@router.get("/login")
async def login_page(request: Request) -> Any:
    """Render the login page."""
    templates = request.app.state.templates
    next_url = request.query_params.get("next", "/")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_url": next_url, "error": None},
    )


@router.post("/login")
async def login_submit(request: Request) -> Any:
    """Handle login form submission with rate limiting."""
    form = await request.form()
    password = str(form.get("password", ""))
    next_url = str(form.get("next", "/"))
    templates = request.app.state.templates
    client_host = request.client.host if request.client else "unknown"

    # Rate limit check
    limit_check = _login_rate_limiter.check(client_host)
    if not limit_check.allowed:
        logger.warning("Rate limited login attempt from %s", client_host)
        return JSONResponse(
            content={"error": "Too many login attempts. Please try again later."},
            status_code=429,
            headers={"Retry-After": str(int(limit_check.retry_after))},
        )

    auth: AuthService | None = request.app.state.services.get("auth")
    if auth is None:
        # No auth configured — redirect directly
        return RedirectResponse(url=next_url, status_code=303)

    if not auth.verify_password(password):
        # Record failed attempt
        _login_rate_limiter.record(client_host)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next_url": next_url, "error": "Invalid password"},
            status_code=401,
        )

    # Successful login — reset rate limiter for this IP
    _login_rate_limiter.reset(client_host)

    # Determine if remote
    is_remote = client_host not in ("127.0.0.1", "::1", "localhost", "")
    user_agent = request.headers.get("user-agent", "")

    session_id = await auth.create_session(
        ip_address=client_host,
        user_agent=user_agent,
        is_remote=is_remote,
    )

    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request) -> Response:
    """Handle logout — delete session and cookie."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    auth: AuthService | None = request.app.state.services.get("auth")
    if auth and session_id:
        await auth.delete_session(session_id)

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
