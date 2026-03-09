"""Tests for agent registry."""

from __future__ import annotations

from cortex.agent.agents.registry import AgentRegistry
from cortex.agent.agents.types import AgentDefinition


class TestRegister:
    def test_register_agent(self) -> None:
        registry = AgentRegistry()
        defn = AgentDefinition(name="test-agent", description="Test")
        registry.register(defn)
        assert "test-agent" in registry.agent_names

    def test_register_with_source(self) -> None:
        registry = AgentRegistry()
        defn = AgentDefinition(name="builtin-agent", description="Builtin")
        registry.register(defn, source="builtin")
        agents = registry.list_agents(source="builtin")
        assert len(agents) == 1

    def test_register_overwrites(self) -> None:
        registry = AgentRegistry()
        defn1 = AgentDefinition(name="test-agent", description="First")
        defn2 = AgentDefinition(name="test-agent", description="Second")
        registry.register(defn1)
        registry.register(defn2)
        assert len(registry) == 1
        assert registry.get_definition("test-agent").description == "Second"


class TestUnregister:
    def test_unregister_existing(self) -> None:
        registry = AgentRegistry()
        defn = AgentDefinition(name="test-agent", description="Test")
        registry.register(defn)
        assert registry.unregister("test-agent") is True
        assert "test-agent" not in registry.agent_names

    def test_unregister_nonexistent(self) -> None:
        registry = AgentRegistry()
        assert registry.unregister("nope") is False


class TestGetDefinition:
    def test_get_existing(self) -> None:
        registry = AgentRegistry()
        defn = AgentDefinition(name="test-agent", description="Test")
        registry.register(defn)
        result = registry.get_definition("test-agent")
        assert result is not None
        assert result.name == "test-agent"

    def test_get_nonexistent(self) -> None:
        registry = AgentRegistry()
        assert registry.get_definition("nope") is None


class TestGetInstance:
    def test_creates_instance(self) -> None:
        registry = AgentRegistry()
        defn = AgentDefinition(name="test-agent", description="Test")
        registry.register(defn)
        instance = registry.get_instance("test-agent")
        assert instance is not None
        assert instance.active is True

    def test_returns_same_instance(self) -> None:
        registry = AgentRegistry()
        defn = AgentDefinition(name="test-agent", description="Test")
        registry.register(defn)
        inst1 = registry.get_instance("test-agent")
        inst2 = registry.get_instance("test-agent")
        assert inst1 is inst2

    def test_nonexistent_returns_none(self) -> None:
        registry = AgentRegistry()
        assert registry.get_instance("nope") is None


class TestListAgents:
    def test_list_all(self) -> None:
        registry = AgentRegistry()
        registry.register(AgentDefinition(name="alpha", description="A"))
        registry.register(AgentDefinition(name="beta", description="B"))
        agents = registry.list_agents()
        assert len(agents) == 2

    def test_filter_by_source(self) -> None:
        registry = AgentRegistry()
        registry.register(AgentDefinition(name="builtin", description="B"), source="builtin")
        registry.register(AgentDefinition(name="dynamic", description="D"), source="dynamic")
        agents = registry.list_agents(source="builtin")
        assert len(agents) == 1
        assert agents[0]["name"] == "builtin"

    def test_empty_registry(self) -> None:
        registry = AgentRegistry()
        assert registry.list_agents() == []
        assert len(registry) == 0
