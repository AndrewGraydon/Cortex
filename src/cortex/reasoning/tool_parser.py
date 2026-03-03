"""Hermes/NousFnCall tool call parser for Qwen3 LLM output.

Extracts <tool_call>{"name":..., "arguments":...}</tool_call> blocks
from LLM-generated text. Handles:
  - Single or multiple tool calls in one response
  - Malformed JSON (best-effort recovery)
  - No tool calls (passthrough)
  - Mixed text and tool calls
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from cortex.agent.types import ToolCall

logger = logging.getLogger(__name__)

# Regex to match <tool_call>...</tool_call> blocks
# Allows optional whitespace and handles both self-closing and paired tags
TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL,
)

# Fallback: match JSON-like objects that look like tool calls
# For when the model omits the XML tags
JSON_TOOL_PATTERN = re.compile(
    r'\{"name"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{[^}]*\})\s*\}',
)


class HermesToolCallParser:
    """Parses Hermes/NousFnCall tool calls from LLM output text.

    Returns (clean_text, tool_calls) where clean_text has tool call
    markup removed for TTS output.
    """

    def parse(self, text: str) -> tuple[str, list[ToolCall]]:
        """Parse LLM output into plain text and tool calls.

        Args:
            text: Raw LLM output that may contain tool call markup.

        Returns:
            Tuple of (clean_text, tool_calls).
            clean_text has tool_call blocks removed and is suitable for TTS.
            tool_calls contains parsed ToolCall objects.
        """
        if not text:
            return ("", [])

        tool_calls: list[ToolCall] = []
        clean_text = text

        # Try XML-tagged tool calls first
        matches = list(TOOL_CALL_PATTERN.finditer(text))

        if matches:
            for match in matches:
                raw_json = match.group(1).strip()
                tc = self._parse_json_tool_call(raw_json, match.group(0))
                if tc is not None:
                    tool_calls.append(tc)
                # Remove the tool call block from text
                clean_text = clean_text.replace(match.group(0), "")

        # Clean up whitespace
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
        clean_text = clean_text.strip()

        return (clean_text, tool_calls)

    def _parse_json_tool_call(self, raw_json: str, raw_text: str) -> ToolCall | None:
        """Parse a JSON tool call body. Returns None on failure."""
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            # Try to fix common JSON issues
            data = self._repair_json(raw_json)
            if data is None:
                logger.warning("Failed to parse tool call JSON: %s", raw_json[:100])
                return None

        name = data.get("name")
        if not name or not isinstance(name, str):
            logger.warning("Tool call missing 'name' field: %s", raw_json[:100])
            return None

        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            # Try to parse arguments as JSON string
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            else:
                arguments = {}

        return ToolCall(name=name, arguments=arguments, raw_text=raw_text)

    def _repair_json(self, raw: str) -> dict[str, Any] | None:
        """Attempt to repair malformed JSON from LLM output.

        Common issues:
          - Trailing commas
          - Single quotes instead of double
          - Unquoted keys
          - Missing closing braces
        """
        # Try fixing trailing commas
        fixed = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            result: dict[str, Any] = json.loads(fixed)
            return result
        except json.JSONDecodeError:
            pass

        # Try replacing single quotes with double
        fixed = raw.replace("'", '"')
        try:
            result2: dict[str, Any] = json.loads(fixed)
            return result2
        except json.JSONDecodeError:
            pass

        # Try adding missing closing brace
        if raw.count("{") > raw.count("}"):
            fixed = raw + "}" * (raw.count("{") - raw.count("}"))
            try:
                result3: dict[str, Any] = json.loads(fixed)
                return result3
            except json.JSONDecodeError:
                pass

        return None
