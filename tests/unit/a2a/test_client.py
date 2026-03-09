"""Tests for A2A client — agent discovery and task delegation."""

from __future__ import annotations

from cortex.a2a.client import A2aClient


class TestClientInit:
    def test_no_discovered_agents(self) -> None:
        client = A2aClient()
        assert client.discovered_agents == {}

    def test_custom_timeout(self) -> None:
        client = A2aClient(timeout=30)
        assert client._timeout == 30


class TestDiscovery:
    async def test_discover_nonexistent_host(self) -> None:
        client = A2aClient(timeout=1)
        result = await client.discover("http://nonexistent.invalid:99999")
        assert result is None

    async def test_discover_all_empty(self) -> None:
        client = A2aClient()
        results = await client.discover_all([])
        assert results == {}


class TestSendTask:
    async def test_send_to_nonexistent_host(self) -> None:
        client = A2aClient(timeout=1)
        result = await client.send_task(
            "http://nonexistent.invalid:99999",
            "Hello",
        )
        assert "error" in result


class TestGetTask:
    async def test_get_from_nonexistent_host(self) -> None:
        client = A2aClient(timeout=1)
        result = await client.get_task(
            "http://nonexistent.invalid:99999",
            "task-id",
        )
        assert "error" in result
