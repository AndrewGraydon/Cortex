"""A2A client — discover agents and delegate tasks via their Agent Cards."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from cortex.a2a.types import AgentCard

logger = logging.getLogger(__name__)


class A2aClient:
    """Client for discovering and interacting with A2A agents.

    Discovers agents via their Agent Cards at /.well-known/agent.json,
    then sends tasks via JSON-RPC to their A2A endpoints.
    """

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout
        self._discovered: dict[str, AgentCard] = {}

    @property
    def discovered_agents(self) -> dict[str, AgentCard]:
        return dict(self._discovered)

    async def discover(self, base_url: str) -> AgentCard | None:
        """Discover an agent by fetching its Agent Card."""
        url = f"{base_url.rstrip('/')}/.well-known/agent.json"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            card = AgentCard(
                name=data.get("name", "Unknown"),
                description=data.get("description", ""),
                url=data.get("url", base_url),
                version=data.get("version", ""),
                protocol_version=data.get("protocolVersion", ""),
                skills=[],
                capabilities=data.get("capabilities", {}),
                authentication=data.get("authentication", {}),
            )
            self._discovered[base_url] = card
            logger.info("Discovered A2A agent: %s at %s", card.name, base_url)
            return card
        except Exception:
            logger.warning("Failed to discover A2A agent at %s", base_url)
            return None

    async def discover_all(self, urls: list[str]) -> dict[str, AgentCard | None]:
        """Discover agents from multiple URLs."""
        results: dict[str, AgentCard | None] = {}
        for url in urls:
            results[url] = await self.discover(url)
        return results

    async def send_task(
        self,
        agent_url: str,
        text: str,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a task to an A2A agent."""
        card = self._discovered.get(agent_url)
        endpoint = card.url if card else f"{agent_url.rstrip('/')}/a2a"

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": "1",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": text}],
                },
            },
        }
        if task_id:
            payload["params"]["id"] = task_id

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json=payload)
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except Exception as e:
            logger.exception("Failed to send A2A task to %s", agent_url)
            return {"error": str(e)}

    async def get_task(
        self,
        agent_url: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Get task status from an A2A agent."""
        card = self._discovered.get(agent_url)
        endpoint = card.url if card else f"{agent_url.rstrip('/')}/a2a"

        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "id": "1",
            "params": {"id": task_id},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json=payload)
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except Exception as e:
            logger.exception("Failed to get A2A task from %s", agent_url)
            return {"error": str(e)}
