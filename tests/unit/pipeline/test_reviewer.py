"""Tests for tool code reviewer."""

from __future__ import annotations

from cortex.agent.tools.pipeline.reviewer import review_tool
from cortex.agent.tools.pipeline.types import PipelineStage, ReviewResult, ToolDraft, ToolSpec

_SENTINEL = object()


def _make_draft(script_code: str | object = _SENTINEL, **spec_kwargs: object) -> ToolDraft:
    """Helper to create a draft with given script code."""
    defaults = {"name": "test-tool", "description": "A test tool", "permission_tier": 2}
    defaults.update(spec_kwargs)
    spec = ToolSpec(**defaults)  # type: ignore[arg-type]

    if script_code is _SENTINEL:
        code = (
            "import json\nimport sys\n\ndata = json.loads(sys.stdin.read())\n"
            'json.dump({"display_text": "ok", "data": data}, sys.stdout)\n'
        )
    else:
        code = str(script_code)

    return ToolDraft(
        spec=spec,
        manifest_yaml=f"name: {spec.name}\ndescription: {spec.description}\n",
        script_code=code,
    )


class TestReviewPassing:
    def test_clean_script_passes(self) -> None:
        draft = _make_draft()
        result = review_tool(draft)
        assert result.passed is True
        assert len(result.issues) == 0

    def test_sets_review_stage(self) -> None:
        draft = _make_draft()
        review_tool(draft)
        assert draft.stage == PipelineStage.REVIEW

    def test_stores_review_result(self) -> None:
        draft = _make_draft()
        review_tool(draft)
        assert draft.review_result is not None
        assert draft.review_result.passed is True


class TestReviewDangerousPatterns:
    def test_os_system(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\nimport os\nos.system('ls')\n"
            "data = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("os.system" in issue for issue in result.issues)

    def test_os_popen(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\nimport os\nos.popen('ls')\n"
            "data = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("os.popen" in issue for issue in result.issues)

    def test_subprocess_shell_true(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\nimport subprocess\n"
            "subprocess.run('ls', shell=True)\n"
            "data = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("shell=True" in issue for issue in result.issues)

    def test_eval(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\neval('1+1')\ndata = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("eval()" in issue for issue in result.issues)

    def test_exec(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\nexec('print(1)')\ndata = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("exec()" in issue for issue in result.issues)

    def test_dunder_import(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\n__import__('os')\ndata = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("__import__" in issue for issue in result.issues)

    def test_requests_library(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\nimport requests\ndata = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("network" in issue.lower() for issue in result.issues)

    def test_socket_access(self) -> None:
        draft = _make_draft(
            "import json\nimport sys\nimport socket\nsocket.socket()\n"
            "data = json.loads(sys.stdin.read())\n"
        )
        result = review_tool(draft)
        assert result.passed is False
        assert any("socket" in issue.lower() for issue in result.issues)


class TestReviewStructuralIssues:
    def test_empty_script(self) -> None:
        draft = _make_draft(script_code="")
        result = review_tool(draft)
        assert result.passed is False
        assert any("empty" in issue.lower() for issue in result.issues)

    def test_empty_manifest(self) -> None:
        spec = ToolSpec(name="test-tool", description="Test")
        draft = ToolDraft(
            spec=spec,
            manifest_yaml="",
            script_code="import json\nimport sys\ndata = json.loads(sys.stdin.read())\n",
        )
        result = review_tool(draft)
        assert result.passed is False

    def test_missing_json_import(self) -> None:
        draft = _make_draft("import sys\ndata = sys.stdin.read()\n")
        result = review_tool(draft)
        assert result.passed is False
        assert any("json" in issue for issue in result.issues)

    def test_missing_stdin(self) -> None:
        draft = _make_draft("import json\nresult = json.dumps({})\n")
        result = review_tool(draft)
        assert result.passed is False
        assert any("stdin" in issue for issue in result.issues)

    def test_low_tier_rejected(self) -> None:
        draft = _make_draft(permission_tier=1)
        result = review_tool(draft)
        assert result.passed is False
        assert any("Tier 2" in issue for issue in result.issues)

    def test_stage_stays_draft_on_failure(self) -> None:
        draft = _make_draft(script_code="")
        review_tool(draft)
        assert draft.stage == PipelineStage.DRAFT


class TestReviewResult:
    def test_review_result_defaults(self) -> None:
        result = ReviewResult(passed=True)
        assert result.passed is True
        assert result.issues == []
        assert result.sandbox_passed is None
        assert result.reviewed_at > 0
