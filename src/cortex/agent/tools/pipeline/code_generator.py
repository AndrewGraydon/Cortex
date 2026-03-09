"""Code generator — ToolSpec to TOOL.yaml + scripts/run.py.

Template-based generation that works without LLM.
Produces a valid TOOL.yaml manifest and a Python entry point script.
"""

from __future__ import annotations

import yaml

from cortex.agent.tools.pipeline.types import ToolDraft, ToolSpec


def generate_code(spec: ToolSpec) -> ToolDraft:
    """Generate TOOL.yaml and scripts/run.py from a ToolSpec.

    Uses template-based generation (no LLM required).

    Args:
        spec: Tool specification.

    Returns:
        ToolDraft with manifest_yaml and script_code populated.
    """
    manifest = _build_manifest(spec)
    manifest_yaml = yaml.dump(manifest, default_flow_style=False, sort_keys=False)
    script_code = _build_script(spec)

    return ToolDraft(
        spec=spec,
        manifest_yaml=manifest_yaml,
        script_code=script_code,
    )


def _build_manifest(spec: ToolSpec) -> dict[str, object]:
    """Build a TOOL.yaml manifest dict from a ToolSpec."""
    manifest: dict[str, object] = {
        "name": spec.name,
        "description": spec.description,
        "version": 1,
        "permission_tier": spec.permission_tier,
        "entry_point": "scripts/run.py",
        "timeout_seconds": spec.timeout_seconds,
    }

    if spec.keywords:
        manifest["keywords"] = spec.keywords

    if spec.triggers:
        manifest["triggers"] = spec.triggers

    if spec.parameters:
        manifest["parameters"] = spec.parameters

    return manifest


def _build_script(spec: ToolSpec) -> str:
    """Build a Python entry point script from a ToolSpec."""
    # Extract parameter names for the template
    param_names = list(spec.parameters.keys()) if spec.parameters else []

    lines = [
        f'"""Auto-generated tool script: {spec.name}."""',
        "",
        "import json",
        "import sys",
        "",
        "",
        "def main() -> None:",
        f'    """Entry point for {spec.name}."""',
        "    data = json.loads(sys.stdin.read())",
        "",
    ]

    # Add parameter extraction
    for param in param_names:
        lines.append(f'    {param} = data.get("{param}", "")')

    if param_names:
        lines.append("")

    # Add result construction
    lines.extend(
        [
            "    # TODO: Implement tool logic here",
            f'    result_text = "{spec.name} executed successfully"',
            "",
            "    result = {",
            '        "display_text": result_text,',
            '        "data": data,',
            "    }",
            "    json.dump(result, sys.stdout)",
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
            "",
        ]
    )

    return "\n".join(lines)
