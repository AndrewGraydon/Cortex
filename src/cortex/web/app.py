"""FastAPI application factory for Cortex web UI.

Creates the app with Jinja2 templates, static file serving (DaisyUI + HTMX via CDN),
health endpoint, auth routes, session middleware, and route mounting.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cortex.config import CortexConfig, load_config
from cortex.web.api.a2a import router as a2a_router
from cortex.web.api.approvals import router as approvals_router
from cortex.web.api.auth_routes import router as auth_router
from cortex.web.api.calendar import router as calendar_router
from cortex.web.api.chat import router as chat_router
from cortex.web.api.dashboard import router as dashboard_router
from cortex.web.api.health import router as health_router
from cortex.web.api.knowledge import router as knowledge_router
from cortex.web.api.network_security import router as network_security_router
from cortex.web.api.notifications import router as notifications_router
from cortex.web.api.power import router as power_router
from cortex.web.api.security import router as security_router
from cortex.web.api.settings import router as settings_router
from cortex.web.api.tool_pipeline import router as tool_pipeline_router
from cortex.web.api.tools import router as tools_router
from cortex.web.dependencies import init_services
from cortex.web.middleware import AuthMiddleware

logger = logging.getLogger(__name__)

# Resolve paths relative to this file
_WEB_DIR = Path(__file__).parent
_FRONTEND_DIR = _WEB_DIR / "frontend"
_TEMPLATE_DIR = _FRONTEND_DIR / "templates"
_STATIC_DIR = _FRONTEND_DIR / "static"


def create_app(
    config: CortexConfig | None = None,
    enable_auth: bool = True,
    **service_overrides: Any,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Cortex configuration. If None, loads from default paths.
        enable_auth: Whether to enable authentication middleware.
        **service_overrides: Override services for testing (e.g., npu=MockNpuService()).
    """
    if config is None:
        config = load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """App lifespan — initializes services on startup."""
        container = init_services(config, **service_overrides)
        # Start auth service if provided
        auth_service = container.get("auth")
        if auth_service:
            await auth_service.start()
        app.state.services = container
        app.state.config = config
        logger.info("Cortex web UI started on %s:%d", config.web.host, config.web.port)
        yield
        if auth_service:
            await auth_service.stop()
        logger.info("Cortex web UI shutting down")

    app = FastAPI(
        title="Cortex",
        description="Local AI voice assistant web interface",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Jinja2 templates
    templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
    app.state.templates = templates

    # Authentication middleware (before routes)
    if enable_auth:
        app.add_middleware(AuthMiddleware)

    # Static files
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # API routes (health is unauthenticated, auth routes exempt)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(dashboard_router)
    app.include_router(approvals_router)
    app.include_router(notifications_router)
    app.include_router(tools_router)
    app.include_router(settings_router)
    app.include_router(security_router)
    app.include_router(calendar_router)
    app.include_router(knowledge_router)
    app.include_router(a2a_router)
    app.include_router(tool_pipeline_router)
    app.include_router(power_router)
    app.include_router(network_security_router)

    # Index route
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Landing page — renders the index template."""
        return templates.TemplateResponse(
            request,
            "index.html",
            {"title": "Cortex"},
        )

    return app
