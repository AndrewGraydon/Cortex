"""Spec generator — natural language or structured input to ToolSpec.

Works without LLM via template-based generation from structured input.
Optional LLM parameter for natural language spec generation (Phase 5+).
"""

from __future__ import annotations

import re
from typing import Any

from cortex.agent.tools.pipeline.types import ToolSpec


def generate_spec(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    permission_tier: int = 2,
    timeout_seconds: float = 10.0,
    keywords: list[str] | None = None,
    triggers: list[str] | None = None,
) -> ToolSpec:
    """Create a ToolSpec from structured input.

    Args:
        name: Tool name (must be valid identifier with hyphens).
        description: Human-readable description.
        parameters: Parameter definitions {name: {type, description, required}}.
        permission_tier: Permission level (default 2 for user-created).
        timeout_seconds: Execution timeout.
        keywords: Keywords for intent matching.
        triggers: Regex patterns for intent matching.

    Returns:
        Validated ToolSpec.

    Raises:
        ValueError: If name is invalid or description is empty.
    """
    # Validate name: alphanumeric + hyphens, 2-50 chars
    if not re.match(r"^[a-z][a-z0-9\-]{1,49}$", name):
        msg = (
            f"Invalid tool name '{name}': must be 2-50 chars, "
            "lowercase alphanumeric + hyphens, start with letter"
        )
        raise ValueError(msg)

    if not description.strip():
        msg = "Tool description cannot be empty"
        raise ValueError(msg)

    # Ensure permission tier is at least 2 for user-created tools
    effective_tier = max(permission_tier, 2)

    return ToolSpec(
        name=name,
        description=description.strip(),
        parameters=parameters or {},
        permission_tier=effective_tier,
        timeout_seconds=timeout_seconds,
        keywords=keywords or [],
        triggers=triggers or [],
    )


def generate_spec_from_text(text: str) -> ToolSpec:
    """Generate a ToolSpec from a natural language description.

    Uses simple heuristics to extract tool name, description, and parameters.
    For full LLM-based generation, use the LLM pipeline (Phase 5+).

    Args:
        text: Natural language tool description.

    Returns:
        ToolSpec with extracted fields.

    Raises:
        ValueError: If text is too short to extract a useful spec.
    """
    text = text.strip()
    if len(text) < 10:
        msg = "Description too short to generate a tool spec"
        raise ValueError(msg)

    # Extract a name from the first few words
    words = re.findall(r"[a-z]+", text.lower())
    # Skip common filler words
    skip = {"a", "an", "the", "that", "which", "to", "for", "and", "or", "create", "make", "build"}
    name_words = [w for w in words[:6] if w not in skip][:3]
    if not name_words:
        name_words = ["custom-tool"]

    name = "-".join(name_words)
    # Ensure valid name format
    if not re.match(r"^[a-z]", name):
        name = "tool-" + name

    return ToolSpec(
        name=name,
        description=text,
        permission_tier=2,
    )
