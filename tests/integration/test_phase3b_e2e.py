"""Phase 3b E2E tests — validates exit criteria and full integration.

Exit Criteria:
1. CalDAV calendar query returns results via both voice and web UI
2. A2A Agent Card served at /.well-known/agent.json
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from cortex.a2a.agent_card import AgentCardBuilder
from cortex.a2a.server import A2aServer
from cortex.agent.router import IntentRouter
from cortex.agent.tools.builtin.calendar_tool import CalendarQueryTool, set_calendar_backend
from cortex.agent.tools.registry import ToolRegistry
from cortex.agent.types import IntentType
from cortex.config import CortexConfig
from cortex.external.calendar.mock import MockCalendarAdapter
from cortex.external.protocols import ExternalServiceManager
from cortex.external.types import CalendarEvent
from cortex.web.app import create_app

# --- Fixtures ---


@pytest.fixture
def mock_calendar() -> MockCalendarAdapter:
    adapter = MockCalendarAdapter()
    now = datetime.now(tz=UTC)
    adapter._events.append(
        CalendarEvent(
            uid="e2e-1",
            summary="Team Standup",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=1, minutes=30),
        )
    )
    adapter._events.append(
        CalendarEvent(
            uid="e2e-2",
            summary="Lunch with Alice",
            start=now + timedelta(hours=3),
            end=now + timedelta(hours=4),
        )
    )
    return adapter


@pytest.fixture
def ext_manager(mock_calendar: MockCalendarAdapter) -> ExternalServiceManager:
    manager = ExternalServiceManager()
    manager.register(mock_calendar)
    return manager


@pytest.fixture
def tool_registry(mock_calendar: MockCalendarAdapter) -> ToolRegistry:
    set_calendar_backend(mock_calendar)
    registry = ToolRegistry()
    registry.register(CalendarQueryTool())
    return registry


@pytest.fixture
def full_client(
    ext_manager: ExternalServiceManager,
    tool_registry: ToolRegistry,
) -> Generator[TestClient]:
    """Full integration client with calendar, A2A, and tools."""
    config = CortexConfig()
    card = AgentCardBuilder().add_default_skills().build()
    a2a_server = A2aServer()
    app = create_app(
        config=config,
        enable_auth=False,
        external_service_manager=ext_manager,
        tool_registry=tool_registry,
        agent_card=card,
        a2a_server=a2a_server,
    )
    with TestClient(app) as c:
        yield c
    set_calendar_backend(None)


# --- Exit Criterion 1: CalDAV Calendar Query ---


class TestCalDAVCalendarE2E:
    """EC1: CalDAV calendar query returns results via both voice and web UI."""

    def test_calendar_query_via_web_api(self, full_client: TestClient) -> None:
        """Calendar events are accessible via the web API."""
        resp = full_client.get("/api/calendar/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert len(data["events"]) == 2
        summaries = {e["summary"] for e in data["events"]}
        assert "Team Standup" in summaries
        assert "Lunch with Alice" in summaries

    async def test_calendar_query_via_tool(self, mock_calendar: MockCalendarAdapter) -> None:
        """Calendar events are accessible via the CalendarQueryTool (voice path)."""
        set_calendar_backend(mock_calendar)
        tool = CalendarQueryTool()
        result = await tool.execute({"days_ahead": 7})
        assert result.success is True
        assert "Team Standup" in result.display_text
        set_calendar_backend(None)

    def test_calendar_intent_routes_correctly(self) -> None:
        """Calendar-related utterances are routed to the calendar tool."""
        router = IntentRouter()
        d = router.route("what's on my calendar")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match is not None
        assert d.intent_match.intent_id == "calendar_query"
        assert d.tool_hints == ["calendar_query"]

    def test_calendar_create_intent_routes(self) -> None:
        """Calendar create utterances route correctly."""
        router = IntentRouter()
        d = router.route("schedule a meeting for tomorrow")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_create"

    def test_calendar_web_page(self, full_client: TestClient) -> None:
        """Calendar web page renders."""
        resp = full_client.get("/calendar")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_calendar_create_via_web(self, full_client: TestClient) -> None:
        """Events can be created via the web API."""
        resp = full_client.post(
            "/api/calendar/events",
            json={
                "summary": "E2E Created Event",
                "start": "2025-12-15T10:00:00+00:00",
            },
        )
        data = resp.json()
        assert data["success"] is True
        assert data["event"]["summary"] == "E2E Created Event"


# --- Exit Criterion 2: A2A Agent Card ---


class TestA2AAgentCardE2E:
    """EC2: A2A Agent Card served at /.well-known/agent.json."""

    def test_agent_card_served(self, full_client: TestClient) -> None:
        """Agent Card is accessible at the well-known URL."""
        resp = full_client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Cortex"

    def test_agent_card_has_skills(self, full_client: TestClient) -> None:
        """Agent Card includes skills."""
        resp = full_client.get("/.well-known/agent.json")
        data = resp.json()
        assert len(data["skills"]) > 0
        skill_ids = {s["id"] for s in data["skills"]}
        assert "general" in skill_ids
        assert "pim" in skill_ids

    def test_agent_card_has_protocol_version(self, full_client: TestClient) -> None:
        """Agent Card includes protocol version."""
        resp = full_client.get("/.well-known/agent.json")
        data = resp.json()
        assert "protocolVersion" in data

    def test_agent_card_has_url(self, full_client: TestClient) -> None:
        """Agent Card includes the A2A endpoint URL."""
        resp = full_client.get("/.well-known/agent.json")
        data = resp.json()
        assert "url" in data
        assert "/a2a" in data["url"]

    def test_a2a_endpoint_accepts_tasks(self, full_client: TestClient) -> None:
        """A2A endpoint accepts and processes tasks."""
        resp = full_client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "e2e-1",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "What's on my calendar?"}],
                    },
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert data["result"]["status"]["state"] == "completed"


# --- MCP Server Integration ---


class TestMcpServerE2E:
    """MCP server exposes tools when configured."""

    def test_tools_api_lists_tools(self, full_client: TestClient) -> None:
        """Tool registry tools are visible via the web API."""
        resp = full_client.get("/api/tools")
        data = resp.json()
        tool_names = {t["name"] for t in data["tools"]}
        assert "calendar_query" in tool_names


# --- External Services Integration ---


class TestExternalServicesE2E:
    """Dashboard and settings integration with external services."""

    def test_dashboard_services_endpoint(self, full_client: TestClient) -> None:
        """Dashboard services API reports external service status."""
        resp = full_client.get("/api/dashboard/services")
        data = resp.json()
        assert data["configured"] is True
        # A2A should be listed
        service_names = {s["name"] for s in data["services"]}
        assert "a2a" in service_names

    def test_settings_includes_external_services(self, full_client: TestClient) -> None:
        """Settings API includes external services configuration."""
        resp = full_client.get("/api/settings")
        data = resp.json()
        settings = data["settings"]
        assert "external_services" in settings

    def test_settings_includes_mcp(self, full_client: TestClient) -> None:
        """Settings API includes MCP configuration."""
        resp = full_client.get("/api/settings/agent")
        data = resp.json()
        assert "mcp" in data["data"]

    def test_settings_includes_a2a(self, full_client: TestClient) -> None:
        """Settings API includes A2A configuration."""
        resp = full_client.get("/api/settings/agent")
        data = resp.json()
        assert "a2a" in data["data"]

    def test_health_endpoint_ok(self, full_client: TestClient) -> None:
        """Health endpoint returns OK."""
        resp = full_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "healthy")
