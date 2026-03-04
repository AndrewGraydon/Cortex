"""Chat API — page route and WebSocket streaming endpoint.

The chat page is the primary web interface, equivalent to the voice pipeline.
Text input → AgentProcessor → streamed response via WebSocket.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from cortex.web.chat_session import WebChatSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Active WebSocket sessions (tab → WebChatSession)
_sessions: dict[str, WebChatSession] = {}


def _get_or_create_session(session_id: str) -> WebChatSession:
    """Get an existing chat session or create a new one."""
    if session_id not in _sessions:
        _sessions[session_id] = WebChatSession(session_id=session_id)
    return _sessions[session_id]


def _remove_session(session_id: str) -> None:
    """Remove a chat session on disconnect."""
    _sessions.pop(session_id, None)


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request) -> Any:
    """Render the chat page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"title": "Chat — Cortex"},
    )


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming chat.

    Protocol:
    - Client sends JSON: {"message": "user text"}
    - Server sends HTML partials for HTMX to swap into the DOM
    - Each response is a complete chat bubble div
    """
    await websocket.accept()

    # Create a unique session for this WebSocket connection
    chat_session = WebChatSession()
    session_id = chat_session.session_id
    _sessions[session_id] = chat_session
    logger.info("WebSocket chat connected: %s", session_id)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
                message = data.get("message", "").strip()
            except (json.JSONDecodeError, AttributeError):
                # HTMX ws extension sends form-encoded or plain text
                message = raw.strip()

            if not message:
                continue

            # Record user message
            chat_session.add_user_message(message)

            # Send user bubble
            user_html = _render_user_bubble(message)
            await websocket.send_text(user_html)

            # Process through AgentProcessor
            services = websocket.app.state.services
            processor = services.get("agent_processor")

            if processor:
                try:
                    response = await processor.process(message, chat_session.voice_session)
                    reply = chat_session.process_response(response)
                except Exception:
                    logger.exception("AgentProcessor error for session %s", session_id)
                    reply = "Sorry, I encountered an error processing your request."
                    chat_session.add_assistant_message(reply)
            else:
                # No processor — echo for testing
                reply = f"Echo: {message}"
                chat_session.add_assistant_message(reply)

            # Send assistant bubble
            assistant_html = _render_assistant_bubble(reply)
            await websocket.send_text(assistant_html)

    except WebSocketDisconnect:
        logger.info("WebSocket chat disconnected: %s", session_id)
    except Exception:
        logger.exception("WebSocket error for session %s", session_id)
    finally:
        _remove_session(session_id)


def _render_user_bubble(text: str) -> str:
    """Render a user chat bubble as HTML partial."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div id="messages" hx-swap-oob="beforeend">'
        '<div class="chat chat-end">'
        f'<div class="chat-bubble chat-bubble-primary chat-bubble-enter">{escaped}</div>'
        "</div>"
        "</div>"
    )


def _render_assistant_bubble(text: str) -> str:
    """Render an assistant chat bubble as HTML partial."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div id="messages" hx-swap-oob="beforeend">'
        '<div class="chat chat-start">'
        f'<div class="chat-bubble chat-bubble-enter">{escaped}</div>'
        "</div>"
        "</div>"
    )
