"""Notification center — page and WebSocket push endpoint.

Bridges the existing NotificationService to web clients.
Notifications are pushed via WebSocket as HTML partials for real-time display.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])

# Active WebSocket notification clients
_notification_clients: list[WebSocket] = []


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request) -> Any:
    """Render the notification center page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "notifications.html",
        {"title": "Notifications — Cortex"},
    )


@router.get("/api/notifications")
async def get_notifications(request: Request) -> dict[str, Any]:
    """Return recent notifications."""
    services = request.app.state.services
    notification_svc = services.get("notification_service")

    if notification_svc is None:
        return {"notifications": []}

    entries = notification_svc.get_recent(limit=50)
    return {
        "notifications": [
            {
                "id": n.id,
                "timestamp": n.timestamp,
                "title": n.title,
                "message": n.message,
                "priority": n.priority,
                "read": n.read,
                "source": n.source,
            }
            for n in entries
        ]
    }


@router.websocket("/ws/notifications")
async def notification_websocket(websocket: WebSocket) -> None:
    """WebSocket for real-time notification push.

    Clients connect and receive HTML notification toasts as they occur.
    """
    await websocket.accept()
    _notification_clients.append(websocket)
    logger.info("Notification WebSocket connected (%d total)", len(_notification_clients))

    try:
        # Keep connection alive, listen for acks
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Notification WebSocket error")
    finally:
        if websocket in _notification_clients:
            _notification_clients.remove(websocket)
        logger.info(
            "Notification WebSocket disconnected (%d remaining)",
            len(_notification_clients),
        )


async def broadcast_notification(
    title: str,
    message: str,
    priority: int = 1,
) -> None:
    """Push a notification to all connected WebSocket clients.

    Called by the NotificationService bridge when new notifications arrive.
    """
    html = _render_toast(title, message, priority)
    disconnected: list[WebSocket] = []
    for ws in _notification_clients:
        try:
            await ws.send_text(html)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _notification_clients.remove(ws)


def _render_toast(title: str, message: str, priority: int) -> str:
    """Render a notification toast as HTML partial."""
    alert_class = "alert-info"
    if priority >= 3:
        alert_class = "alert-error"
    elif priority >= 2:
        alert_class = "alert-warning"

    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped_msg = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return (
        '<div id="toast-container" hx-swap-oob="afterbegin">'
        f'<div class="alert {alert_class} toast-enter mb-2">'
        f"<div><strong>{escaped_title}</strong><p>{escaped_msg}</p></div>"
        "</div>"
        "</div>"
    )
