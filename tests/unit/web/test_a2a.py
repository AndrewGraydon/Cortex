"""Tests for A2A web API routes — Agent Card and JSON-RPC endpoint."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from cortex.a2a.agent_card import AgentCardBuilder
from cortex.a2a.server import A2aServer
from cortex.config import CortexConfig
from cortex.web.app import create_app


@pytest.fixture
def client_with_a2a() -> Generator[TestClient]:
    """Client with A2A configured."""
    config = CortexConfig()
    card = AgentCardBuilder().add_default_skills().build()
    server = A2aServer()
    app = create_app(
        config=config,
        enable_auth=False,
        agent_card=card,
        a2a_server=server,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_a2a() -> Generator[TestClient]:
    """Client with no A2A configured."""
    config = CortexConfig()
    app = create_app(config=config, enable_auth=False)
    with TestClient(app) as c:
        yield c


class TestAgentCardEndpoint:
    def test_agent_card_returns_json(self, client_with_a2a: TestClient) -> None:
        resp = client_with_a2a.get("/.well-known/agent.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Cortex"
        assert "skills" in data
        assert len(data["skills"]) > 0

    def test_agent_card_has_required_fields(self, client_with_a2a: TestClient) -> None:
        resp = client_with_a2a.get("/.well-known/agent.json")
        data = resp.json()
        assert "name" in data
        assert "description" in data
        assert "url" in data
        assert "protocolVersion" in data
        assert "capabilities" in data

    def test_agent_card_skills_have_ids(self, client_with_a2a: TestClient) -> None:
        resp = client_with_a2a.get("/.well-known/agent.json")
        data = resp.json()
        for skill in data["skills"]:
            assert "id" in skill
            assert "name" in skill
            assert "description" in skill

    def test_agent_card_not_configured(self, client_no_a2a: TestClient) -> None:
        resp = client_no_a2a.get("/.well-known/agent.json")
        assert resp.status_code == 503

    def test_agent_card_content_type(self, client_with_a2a: TestClient) -> None:
        resp = client_with_a2a.get("/.well-known/agent.json")
        assert "application/json" in resp.headers["content-type"]


class TestA2aEndpoint:
    def test_send_task(self, client_with_a2a: TestClient) -> None:
        resp = client_with_a2a.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Hello"}],
                    },
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert data["result"]["status"]["state"] == "completed"

    def test_get_task(self, client_with_a2a: TestClient) -> None:
        # First create a task
        client_with_a2a.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "id": "web-task-1",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Test"}],
                    },
                },
            },
        )
        # Then retrieve it
        resp = client_with_a2a.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "id": "2",
                "params": {"id": "web-task-1"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["id"] == "web-task-1"

    def test_unknown_method(self, client_with_a2a: TestClient) -> None:
        resp = client_with_a2a.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "invalid/method",
                "id": "1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    def test_a2a_not_configured(self, client_no_a2a: TestClient) -> None:
        resp = client_no_a2a.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_invalid_json_body(self, client_with_a2a: TestClient) -> None:
        resp = client_with_a2a.post(
            "/a2a",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32700
