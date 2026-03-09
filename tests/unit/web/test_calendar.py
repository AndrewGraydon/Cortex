"""Tests for calendar web API routes."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.external.calendar.mock import MockCalendarAdapter
from cortex.external.protocols import ExternalServiceManager
from cortex.external.types import CalendarEvent
from cortex.web.app import create_app


@pytest.fixture
def mock_adapter() -> MockCalendarAdapter:
    return MockCalendarAdapter()


@pytest.fixture
def ext_manager(mock_adapter: MockCalendarAdapter) -> ExternalServiceManager:
    manager = ExternalServiceManager()
    manager.register(mock_adapter)
    return manager


@pytest.fixture
def client(ext_manager: ExternalServiceManager) -> Generator[TestClient]:
    config = CortexConfig()
    app = create_app(
        config=config,
        enable_auth=False,
        external_service_manager=ext_manager,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_calendar() -> Generator[TestClient]:
    """Client with no calendar adapter registered."""
    config = CortexConfig()
    app = create_app(config=config, enable_auth=False)
    with TestClient(app) as c:
        yield c


def _make_event(
    uid: str = "web-1",
    summary: str = "Web Event",
    hours_from_now: float = 1,
    **kwargs: Any,
) -> CalendarEvent:
    now = datetime.now(tz=UTC)
    return CalendarEvent(
        uid=uid,
        summary=summary,
        start=now + timedelta(hours=hours_from_now),
        end=now + timedelta(hours=hours_from_now + 1),
        **kwargs,
    )


# --- Page routes ---


class TestCalendarPage:
    def test_calendar_page_returns_html(self, client: TestClient) -> None:
        resp = client.get("/calendar")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Calendar" in resp.text


# --- GET /api/calendar/events ---


class TestListEvents:
    def test_no_calendar_configured(self, client_no_calendar: TestClient) -> None:
        resp = client_no_calendar.get("/api/calendar/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["configured"] is False

    def test_empty_calendar(self, client: TestClient) -> None:
        resp = client.get("/api/calendar/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["configured"] is True

    def test_returns_events(
        self,
        client: TestClient,
        mock_adapter: MockCalendarAdapter,
    ) -> None:
        # Add event directly to mock adapter's internal list
        mock_adapter._events.append(_make_event(uid="w1", summary="Web Meeting"))

        resp = client.get("/api/calendar/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["uid"] == "w1"
        assert data["events"][0]["summary"] == "Web Meeting"

    def test_days_ahead_parameter(
        self,
        client: TestClient,
        mock_adapter: MockCalendarAdapter,
    ) -> None:
        mock_adapter._events.append(_make_event(uid="near", hours_from_now=12))
        mock_adapter._events.append(_make_event(uid="far", hours_from_now=10 * 24))

        resp = client.get("/api/calendar/events?days_ahead=2")
        data = resp.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["uid"] == "near"

    def test_event_json_format(
        self,
        client: TestClient,
        mock_adapter: MockCalendarAdapter,
    ) -> None:
        mock_adapter._events.append(
            CalendarEvent(
                uid="fmt-1",
                summary="Formatted",
                start=datetime.now(tz=UTC) + timedelta(hours=1),
                end=datetime.now(tz=UTC) + timedelta(hours=2),
                location="Room A",
                description="A meeting",
            )
        )

        resp = client.get("/api/calendar/events")
        event = resp.json()["events"][0]
        assert "uid" in event
        assert "summary" in event
        assert "start" in event
        assert "end" in event
        assert "location" in event
        assert "description" in event
        assert "all_day" in event
        assert "display" in event


# --- POST /api/calendar/events ---


class TestCreateEvent:
    def test_no_calendar_configured(self, client_no_calendar: TestClient) -> None:
        resp = client_no_calendar.post(
            "/api/calendar/events",
            json={"summary": "Test", "start": "2025-06-15T14:00:00Z"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    def test_create_success(self, client: TestClient) -> None:
        resp = client.post(
            "/api/calendar/events",
            json={"summary": "New Event", "start": "2025-06-15T14:00:00+00:00"},
        )
        data = resp.json()
        assert data["success"] is True
        assert data["event"]["summary"] == "New Event"

    def test_create_missing_summary(self, client: TestClient) -> None:
        resp = client.post(
            "/api/calendar/events",
            json={"start": "2025-06-15T14:00:00Z"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "summary" in data["error"].lower()

    def test_create_invalid_start(self, client: TestClient) -> None:
        resp = client.post(
            "/api/calendar/events",
            json={"summary": "Test", "start": "bad-date"},
        )
        data = resp.json()
        assert data["success"] is False

    def test_create_with_duration(self, client: TestClient) -> None:
        resp = client.post(
            "/api/calendar/events",
            json={
                "summary": "Long Meeting",
                "start": "2025-06-15T10:00:00+00:00",
                "duration_minutes": 120,
            },
        )
        data = resp.json()
        assert data["success"] is True


# --- DELETE /api/calendar/events/{uid} ---


class TestDeleteEvent:
    def test_no_calendar_configured(self, client_no_calendar: TestClient) -> None:
        resp = client_no_calendar.delete("/api/calendar/events/some-uid")
        data = resp.json()
        assert data["success"] is False

    def test_delete_existing(
        self,
        client: TestClient,
        mock_adapter: MockCalendarAdapter,
    ) -> None:
        mock_adapter._events.append(_make_event(uid="del-1"))

        resp = client.delete("/api/calendar/events/del-1")
        data = resp.json()
        assert data["success"] is True

    def test_delete_nonexistent(self, client: TestClient) -> None:
        resp = client.delete("/api/calendar/events/nonexistent")
        data = resp.json()
        assert data["success"] is False
