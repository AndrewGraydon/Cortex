"""Tests for tool specification generator."""

from __future__ import annotations

import pytest

from cortex.agent.tools.pipeline.spec_generator import generate_spec, generate_spec_from_text


class TestGenerateSpec:
    def test_basic_spec(self) -> None:
        spec = generate_spec(name="my-tool", description="A test tool")
        assert spec.name == "my-tool"
        assert spec.description == "A test tool"
        assert spec.permission_tier == 2

    def test_with_parameters(self) -> None:
        params = {"query": {"type": "string", "required": True, "description": "Search query"}}
        spec = generate_spec(name="search-tool", description="Search something", parameters=params)
        assert "query" in spec.parameters
        assert spec.parameters["query"]["type"] == "string"

    def test_with_keywords(self) -> None:
        spec = generate_spec(
            name="weather-tool", description="Get weather", keywords=["weather", "forecast"]
        )
        assert "weather" in spec.keywords

    def test_with_triggers(self) -> None:
        spec = generate_spec(
            name="timer-tool",
            description="Set timer",
            triggers=[r"set\s+timer"],
        )
        assert len(spec.triggers) == 1

    def test_enforces_minimum_tier(self) -> None:
        spec = generate_spec(name="my-tool", description="Test", permission_tier=0)
        assert spec.permission_tier == 2

    def test_allows_higher_tier(self) -> None:
        spec = generate_spec(name="my-tool", description="Test", permission_tier=3)
        assert spec.permission_tier == 3

    def test_custom_timeout(self) -> None:
        spec = generate_spec(name="my-tool", description="Test", timeout_seconds=30.0)
        assert spec.timeout_seconds == 30.0

    def test_invalid_name_too_short(self) -> None:
        with pytest.raises(ValueError, match="Invalid tool name"):
            generate_spec(name="a", description="Test")

    def test_invalid_name_uppercase(self) -> None:
        with pytest.raises(ValueError, match="Invalid tool name"):
            generate_spec(name="MyTool", description="Test")

    def test_invalid_name_spaces(self) -> None:
        with pytest.raises(ValueError, match="Invalid tool name"):
            generate_spec(name="my tool", description="Test")

    def test_empty_description(self) -> None:
        with pytest.raises(ValueError, match="description cannot be empty"):
            generate_spec(name="my-tool", description="")

    def test_whitespace_description(self) -> None:
        with pytest.raises(ValueError, match="description cannot be empty"):
            generate_spec(name="my-tool", description="   ")

    def test_has_timestamp(self) -> None:
        spec = generate_spec(name="my-tool", description="Test")
        assert spec.created_at > 0


class TestGenerateSpecFromText:
    def test_basic_text(self) -> None:
        spec = generate_spec_from_text("Create a tool that checks disk space usage")
        assert spec.name
        assert len(spec.description) > 0
        assert spec.permission_tier == 2

    def test_text_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            generate_spec_from_text("hi")

    def test_name_extraction(self) -> None:
        spec = generate_spec_from_text("Build a weather forecast checker for the Pi")
        assert len(spec.name) > 0
        assert "-" in spec.name or len(spec.name) >= 2

    def test_preserves_full_description(self) -> None:
        text = "Create a tool that monitors CPU temperature and alerts when too high"
        spec = generate_spec_from_text(text)
        assert spec.description == text
