"""Log redactor — structlog processor that strips sensitive data.

Replaces passwords, tokens, API keys, and session IDs with [REDACTED]
in log output. Designed as a structlog processor inserted into the
logging pipeline.
"""

from __future__ import annotations

import re
from collections.abc import MutableMapping
from typing import Any

# Patterns for sensitive data — (regex, replacement)
_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # API keys (common formats)
    (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[\w\-]{8,}["\']?'), r"\1=[REDACTED]"),
    # Bearer tokens
    (re.compile(r"(?i)(bearer\s+)[\w\-._~+/]+=*"), r"\1[REDACTED]"),
    # Passwords in key=value or JSON
    (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s,}\'"]+["\']?'), r"\1=[REDACTED]"),
    # Session IDs (common cookie/header formats)
    (re.compile(r"(?i)(session[_-]?id|sid)\s*[=:]\s*[\w\-]{16,}"), r"\1=[REDACTED]"),
    # Generic tokens
    (re.compile(r'(?i)(token|secret)\s*[=:]\s*["\']?[\w\-._]{8,}["\']?'), r"\1=[REDACTED]"),
    # bcrypt hashes
    (re.compile(r"\$2[aby]?\$\d{1,2}\$[./A-Za-z0-9]{53}"), "[BCRYPT_HASH]"),
]


def redact_string(text: str) -> str:
    """Apply all redaction patterns to a string."""
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any) -> Any:
    """Redact sensitive data from a value (string, dict, or list)."""
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


def log_redactor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor that redacts sensitive data from log events.

    Insert into the structlog processor chain before the renderer.
    """
    # Redact the main event message
    if "event" in event_dict:
        event_dict["event"] = redact_value(event_dict["event"])

    # Redact all other fields
    for key in list(event_dict.keys()):
        if key in ("event", "_record", "_from_structlog"):
            continue
        event_dict[key] = redact_value(event_dict[key])

    return event_dict
