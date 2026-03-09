"""Pipeline types — tool specification, drafts, stages, review results."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any


class PipelineStage(enum.Enum):
    """Lifecycle stage for a tool in the pipeline."""

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    DISABLED = "disabled"


@dataclass
class ToolSpec:
    """Specification for a tool to be created."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    permission_tier: int = 2
    timeout_seconds: float = 10.0
    keywords: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class ToolDraft:
    """A generated tool awaiting review and deployment."""

    spec: ToolSpec
    manifest_yaml: str = ""
    script_code: str = ""
    stage: PipelineStage = PipelineStage.DRAFT
    review_result: ReviewResult | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class ReviewResult:
    """Result of automated code review."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    sandbox_passed: bool | None = None
    reviewed_at: float = field(default_factory=time.time)
