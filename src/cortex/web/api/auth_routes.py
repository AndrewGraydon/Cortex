"""Authentication routes — login/logout pages and form handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from cortex.web.auth import AuthService
from cortex.web.middleware import SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


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
    """Handle login form submission."""
    form = await request.form()
    password = str(form.get("password", ""))
    next_url = str(form.get("next", "/"))
    templates = request.app.state.templates

    auth: AuthService | None = request.app.state.services.get("auth")
    if auth is None:
        # No auth configured — redirect directly
        return RedirectResponse(url=next_url, status_code=303)

    if not auth.verify_password(password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next_url": next_url, "error": "Invalid password"},
            status_code=401,
        )

    # Determine if remote
    client_host = request.client.host if request.client else ""
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
