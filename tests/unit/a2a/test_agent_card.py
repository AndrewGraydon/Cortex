"""Tests for A2A Agent Card builder."""

from __future__ import annotations

from cortex.a2a.agent_card import DEFAULT_SKILLS, AgentCardBuilder
from cortex.a2a.types import A2aSkill, AgentCard


class TestAgentCardBuilder:
    def test_build_returns_agent_card(self) -> None:
        card = AgentCardBuilder().build()
        assert isinstance(card, AgentCard)

    def test_default_name(self) -> None:
        card = AgentCardBuilder().build()
        assert card.name == "Cortex"

    def test_custom_name(self) -> None:
        card = AgentCardBuilder(name="TestBot").build()
        assert card.name == "TestBot"

    def test_default_description(self) -> None:
        card = AgentCardBuilder().build()
        assert "voice assistant" in card.description.lower()

    def test_custom_description(self) -> None:
        card = AgentCardBuilder(description="Custom agent").build()
        assert card.description == "Custom agent"

    def test_url_includes_a2a_endpoint(self) -> None:
        card = AgentCardBuilder(base_url="http://localhost:8000").build()
        assert card.url == "http://localhost:8000/a2a"

    def test_url_strips_trailing_slash(self) -> None:
        card = AgentCardBuilder(base_url="http://localhost:8000/").build()
        assert card.url == "http://localhost:8000/a2a"

    def test_version(self) -> None:
        card = AgentCardBuilder(version="1.0.0").build()
        assert card.version == "1.0.0"


class TestAgentCardSkills:
    def test_no_skills_by_default(self) -> None:
        card = AgentCardBuilder().build()
        assert card.skills == []

    def test_add_skill(self) -> None:
        skill = A2aSkill(id="test", name="Test", description="Test skill")
        card = AgentCardBuilder().add_skill(skill).build()
        assert len(card.skills) == 1
        assert card.skills[0].id == "test"

    def test_add_multiple_skills(self) -> None:
        builder = AgentCardBuilder()
        builder.add_skill(A2aSkill(id="a", name="A", description="Skill A"))
        builder.add_skill(A2aSkill(id="b", name="B", description="Skill B"))
        card = builder.build()
        assert len(card.skills) == 2

    def test_add_default_skills_all(self) -> None:
        card = AgentCardBuilder().add_default_skills().build()
        assert len(card.skills) == len(DEFAULT_SKILLS)

    def test_add_default_skills_subset(self) -> None:
        card = AgentCardBuilder().add_default_skills(["general", "pim"]).build()
        assert len(card.skills) == 2
        ids = {s.id for s in card.skills}
        assert ids == {"general", "pim"}

    def test_add_default_skills_unknown_id(self) -> None:
        card = AgentCardBuilder().add_default_skills(["general", "nonexistent"]).build()
        assert len(card.skills) == 1

    def test_fluent_interface(self) -> None:
        card = (
            AgentCardBuilder()
            .add_default_skills(["general"])
            .set_capabilities(streaming=True)
            .build()
        )
        assert len(card.skills) == 1
        assert card.capabilities["streaming"] is True


class TestAgentCardSerialization:
    def test_to_dict_has_required_fields(self) -> None:
        card = AgentCardBuilder().build()
        d = card.to_dict()
        assert "name" in d
        assert "description" in d
        assert "url" in d
        assert "version" in d
        assert "protocolVersion" in d
        assert "skills" in d
        assert "capabilities" in d
        assert "defaultInputModes" in d
        assert "defaultOutputModes" in d

    def test_to_dict_skills_serialized(self) -> None:
        card = AgentCardBuilder().add_default_skills(["general"]).build()
        d = card.to_dict()
        assert len(d["skills"]) == 1
        skill = d["skills"][0]
        assert "id" in skill
        assert "name" in skill
        assert "description" in skill
        assert "tags" in skill

    def test_to_dict_capabilities(self) -> None:
        card = AgentCardBuilder().set_capabilities(streaming=True).build()
        d = card.to_dict()
        assert d["capabilities"]["streaming"] is True

    def test_to_dict_authentication(self) -> None:
        card = AgentCardBuilder().set_authentication(schemes=["bearer"]).build()
        d = card.to_dict()
        assert d["authentication"]["schemes"] == ["bearer"]


class TestDefaultSkills:
    def test_general_skill_exists(self) -> None:
        assert "general" in DEFAULT_SKILLS

    def test_home_skill_exists(self) -> None:
        assert "home" in DEFAULT_SKILLS

    def test_research_skill_exists(self) -> None:
        assert "research" in DEFAULT_SKILLS

    def test_pim_skill_exists(self) -> None:
        assert "pim" in DEFAULT_SKILLS

    def test_planner_skill_exists(self) -> None:
        assert "planner" in DEFAULT_SKILLS

    def test_skills_have_required_fields(self) -> None:
        for skill in DEFAULT_SKILLS.values():
            assert skill.id
            assert skill.name
            assert skill.description
            assert len(skill.tags) > 0

    def test_skill_to_dict(self) -> None:
        skill = DEFAULT_SKILLS["general"]
        d = skill.to_dict()
        assert d["id"] == "general"
        assert "examples" in d
