"""Tool reviewer — static analysis and sandbox test for generated tools.

Catches dangerous patterns (shell injection, raw network, os.system) before
tools are approved for deployment.
"""

from __future__ import annotations

import re

from cortex.agent.tools.pipeline.types import PipelineStage, ReviewResult, ToolDraft

# Dangerous patterns that should never appear in user-created tools
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\bos\.system\b", "os.system() is not allowed — use subprocess instead"),
    (r"\bos\.popen\b", "os.popen() is not allowed — use subprocess instead"),
    (r"\bsubprocess\..*shell\s*=\s*True", "shell=True is not allowed in subprocess calls"),
    (r"\beval\s*\(", "eval() is not allowed"),
    (r"\bexec\s*\(", "exec() is not allowed"),
    (r"\b__import__\s*\(", "__import__() is not allowed"),
    (r"\bopen\s*\([^)]*,\s*['\"]w", "Writing files is restricted — use /tmp only"),
    (r"\bsocket\.\w+", "Direct socket access is not allowed"),
    (r"\burllib\b", "Direct network access is not allowed — declare network in manifest"),
    (r"\brequests\b", "Direct network access is not allowed — declare network in manifest"),
    (r"\bhttpx\b", "Direct network access is not allowed — declare network in manifest"),
    (r"\baiohttp\b", "Direct network access is not allowed — declare network in manifest"),
]


def review_tool(draft: ToolDraft) -> ReviewResult:
    """Review a tool draft for dangerous patterns.

    Performs static analysis on the generated script code.
    Does NOT execute the tool — sandbox testing is separate.

    Args:
        draft: Tool draft to review.

    Returns:
        ReviewResult with pass/fail and issue list.
    """
    issues: list[str] = []

    # Check manifest
    issues.extend(_check_manifest(draft))

    # Check script code
    issues.extend(_check_script(draft.script_code))

    passed = len(issues) == 0
    result = ReviewResult(passed=passed, issues=issues)

    # Update draft stage
    draft.review_result = result
    if passed:
        draft.stage = PipelineStage.REVIEW
    else:
        draft.stage = PipelineStage.DRAFT  # Needs fixes

    return result


def _check_manifest(draft: ToolDraft) -> list[str]:
    """Check manifest for basic validity."""
    issues: list[str] = []

    if not draft.manifest_yaml.strip():
        issues.append("Manifest YAML is empty")
        return issues

    if not draft.spec.name:
        issues.append("Tool name is required")

    if not draft.spec.description:
        issues.append("Tool description is required")

    if draft.spec.permission_tier < 2:
        issues.append("User-created tools must be Tier 2 or higher")

    return issues


def _check_script(code: str) -> list[str]:
    """Check script code for dangerous patterns."""
    issues: list[str] = []

    if not code.strip():
        issues.append("Script code is empty")
        return issues

    for pattern, message in DANGEROUS_PATTERNS:
        if re.search(pattern, code):
            issues.append(message)

    # Check for reasonable script structure
    if "import json" not in code:
        issues.append("Script should import json for stdin/stdout protocol")

    if "sys.stdin" not in code:
        issues.append("Script should read from sys.stdin for input")

    return issues
