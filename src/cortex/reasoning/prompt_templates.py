"""System prompt templates for the agent pipeline.

Templates are kept intentionally concise for the 2,047 token budget.
The Hermes/NousFnCall tool-calling format is used for Qwen3 models.
"""

from __future__ import annotations

from cortex.reasoning.types import ToolSchema

# Base system prompt (~15 tokens) — always included as P1
# Keep this VERY short: Qwen3-VL-2B's thinking mode activates with complex
# system prompts, consuming the entire 2,047 token budget on <think> tags.
SYSTEM_PROMPT_V1 = "You are Cortex, a helpful voice assistant. Be concise."

# Tool-calling instruction block (~60 tokens) — appended when tools are available
TOOL_INSTRUCTION = """\

You have access to tools. To use a tool, respond with:
<tool_call>{"name": "tool_name", "arguments": {"arg": "value"}}</tool_call>

After a tool result, incorporate it naturally into your spoken response."""

# Tool result injection format
TOOL_RESULT_FORMAT = "\n[Tool Result: {name}] {result}\n"

# Memory injection format
MEMORY_BLOCK_FORMAT = "\n[Memory]\n{memories}\n"


def build_tool_descriptions(tools: list[ToolSchema]) -> str:
    """Format tool schemas for prompt injection.

    Each tool is described in a concise JSON format to minimize token usage.
    ~30-50 tokens per tool.
    """
    if not tools:
        return ""

    lines = ["\nAvailable tools:"]
    for tool in tools:
        desc = f"- {tool.name}: {tool.description}"
        if tool.parameters:
            params = ", ".join(f"{k}({v.get('type', 'any')})" for k, v in tool.parameters.items())
            desc += f" [{params}]"
        lines.append(desc)
    return "\n".join(lines)


def build_system_prompt(
    tools: list[ToolSchema] | None = None,
    memories: list[str] | None = None,
    version: str = "v1",
) -> str:
    """Build the full system prompt with optional tool and memory sections.

    Priority components (always included):
      P1: System prompt base
    Optional components:
      P3: Tool instructions + descriptions (if tools provided)
      P4: Memory block (if memories provided)
    """
    parts = [SYSTEM_PROMPT_V1]

    if tools:
        parts.append(TOOL_INSTRUCTION)
        parts.append(build_tool_descriptions(tools))

    if memories:
        block = "\n".join(f"- {m}" for m in memories)
        parts.append(MEMORY_BLOCK_FORMAT.format(memories=block))

    return "".join(parts)
