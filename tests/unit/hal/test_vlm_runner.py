"""Tests for VLMRunner — Qwen3-VL-2B via axllm serve (OpenAI-compat API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortex.hal.npu.runners.vlm import VLMRunner
from cortex.hal.types import InferenceInputs


class TestVLMRunnerProtocol:
    """Test that VLMRunner satisfies the ModelRunner protocol."""

    def test_model_type(self) -> None:
        runner = VLMRunner()
        assert runner.model_type == "vlm"

    def test_not_loaded_initially(self) -> None:
        runner = VLMRunner()
        assert not runner.is_loaded
        assert runner.memory_mb == 0

    async def test_infer_raises_when_not_loaded(self) -> None:
        runner = VLMRunner()
        with pytest.raises(RuntimeError, match="VLM not loaded"):
            await runner.infer(InferenceInputs(data="test"))

    async def test_infer_stream_raises_when_not_loaded(self) -> None:
        runner = VLMRunner()
        with pytest.raises(RuntimeError, match="VLM not loaded"):
            async for _ in runner.infer_stream(InferenceInputs(data="test")):
                pass  # pragma: no cover

    async def test_load_raises_if_already_loaded(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        with pytest.raises(RuntimeError, match="VLM already loaded"):
            await runner.load(Path("/mock"), {})


class TestMessageBuilding:
    """Test OpenAI message format construction."""

    def test_text_only_message(self) -> None:
        runner = VLMRunner()
        runner._system_prompt = "You are helpful."
        messages = runner._build_messages("Hello", {})
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "You are helpful."}
        assert messages[1] == {"role": "user", "content": "Hello"}

    def test_text_only_no_system_prompt(self) -> None:
        runner = VLMRunner()
        runner._system_prompt = ""
        messages = runner._build_messages("Hello", {})
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "Hello"}

    def test_vision_message_with_image(self) -> None:
        runner = VLMRunner()
        runner._system_prompt = ""
        messages = runner._build_messages("What is this?", {"image_base64": "abc123"})
        assert len(messages) == 1
        content = messages[0]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0]["type"] == "image_url"
        assert "abc123" in content[0]["image_url"]["url"]
        assert content[1] == {"type": "text", "text": "What is this?"}

    def test_vision_message_with_system_prompt(self) -> None:
        runner = VLMRunner()
        runner._system_prompt = "Describe images."
        messages = runner._build_messages("What is this?", {"image_base64": "xyz"})
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert isinstance(messages[1]["content"], list)


class TestRequestBodyBuilding:
    """Test OpenAI request body construction."""

    def test_basic_body(self) -> None:
        runner = VLMRunner()
        messages = [{"role": "user", "content": "Hi"}]
        body = runner._build_request_body(messages, {}, stream=False)
        assert body["model"] == "default"
        assert body["messages"] == messages
        assert body["stream"] is False
        assert "temperature" not in body

    def test_streaming_body(self) -> None:
        runner = VLMRunner()
        messages = [{"role": "user", "content": "Hi"}]
        body = runner._build_request_body(messages, {}, stream=True)
        assert body["stream"] is True

    def test_sampling_params(self) -> None:
        runner = VLMRunner()
        messages = [{"role": "user", "content": "Hi"}]
        params = {
            "temperature": 0.5,
            "top_p": 0.9,
            "max_tokens": 256,
            "repetition_penalty": 1.1,
        }
        body = runner._build_request_body(messages, params, stream=False)
        assert body["temperature"] == 0.5
        assert body["top_p"] == 0.9
        assert body["max_tokens"] == 256
        assert body["repetition_penalty"] == 1.1


class TestThinkTagStripping:
    """Test removal of Qwen3 thinking tags."""

    def test_strip_think_tags(self) -> None:
        text = "<think>Let me think...</think>The answer is 4."
        assert VLMRunner._strip_think_tags(text) == "The answer is 4."

    def test_strip_multiline_think(self) -> None:
        text = "<think>\nStep 1\nStep 2\n</think>\nResult"
        assert VLMRunner._strip_think_tags(text) == "Result"

    def test_no_think_tags(self) -> None:
        text = "Just a normal response."
        assert VLMRunner._strip_think_tags(text) == "Just a normal response."

    def test_empty_after_strip(self) -> None:
        text = "<think>Only thinking</think>"
        assert VLMRunner._strip_think_tags(text) == ""


class TestBinarySearch:
    """Test axllm binary discovery logic."""

    def test_config_override(self, tmp_path: Path) -> None:
        binary = tmp_path / "my_axllm"
        binary.touch()
        binary.chmod(0o755)
        result = VLMRunner._find_binary(tmp_path, {"axllm_binary": str(binary)})
        assert result == binary

    def test_config_override_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="configured path"):
            VLMRunner._find_binary(tmp_path, {"axllm_binary": "/nonexistent/axllm"})

    def test_find_in_model_dir(self, tmp_path: Path) -> None:
        binary = tmp_path / "axllm"
        binary.touch()
        result = VLMRunner._find_binary(tmp_path, {})
        assert result == binary

    def test_find_aarch64_variant(self, tmp_path: Path) -> None:
        binary = tmp_path / "axllm_aarch64"
        binary.touch()
        result = VLMRunner._find_binary(tmp_path, {})
        assert result == binary

    def test_not_found_anywhere(self, tmp_path: Path) -> None:
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(FileNotFoundError, match="not found"),
        ):
            VLMRunner._find_binary(tmp_path, {})

    def test_find_in_path(self, tmp_path: Path) -> None:
        with patch("shutil.which", return_value="/usr/bin/axllm"):
            result = VLMRunner._find_binary(tmp_path, {})
            assert result == Path("/usr/bin/axllm")


class TestInference:
    """Test inference with mocked HTTP client."""

    async def test_infer_text_only(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        runner._system_prompt = ""

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "The answer is 4."},
                    "finish_reason": "stop",
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        runner._client = mock_client

        result = await runner.infer(InferenceInputs(data="What is 2+2?"))
        assert result.data == "The answer is 4."
        assert result.metadata["finish_reason"] == "stop"

    async def test_infer_strips_think_tags(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        runner._system_prompt = ""

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "<think>hmm</think>Four."},
                    "finish_reason": "stop",
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        runner._client = mock_client

        result = await runner.infer(InferenceInputs(data="What is 2+2?"))
        assert result.data == "Four."

    async def test_infer_with_vision(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        runner._system_prompt = ""

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "A red square."},
                    "finish_reason": "stop",
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        runner._client = mock_client

        result = await runner.infer(
            InferenceInputs(
                data="What is this?",
                params={"image_base64": "fake_b64_data"},
            )
        )
        assert result.data == "A red square."

        # Verify the request included image content
        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        user_msg = body["messages"][-1]
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][0]["type"] == "image_url"


class TestSSEParsing:
    """Test SSE stream parsing in infer_stream."""

    async def test_stream_basic(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        runner._system_prompt = ""

        # Simulate SSE lines
        sse_lines = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"!"},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = mock_aiter_lines

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        runner._client = mock_client

        chunks = []
        async for output in runner.infer_stream(InferenceInputs(data="Hi")):
            chunks.append(str(output.data))

        full_text = "".join(chunks)
        assert full_text == "Hello world!"
        assert len(chunks) == 3

    async def test_stream_strips_think_tags(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        runner._system_prompt = ""

        sse_lines = [
            'data: {"choices":[{"delta":{"content":"<think>"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"reasoning"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"</think>"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"Answer."},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = mock_aiter_lines

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        runner._client = mock_client

        chunks = []
        async for output in runner.infer_stream(InferenceInputs(data="test")):
            chunks.append(str(output.data))

        full_text = "".join(chunks)
        assert "think" not in full_text
        assert "Answer." in full_text


class TestResetContext:
    """Test context reset behavior."""

    async def test_reset_updates_system_prompt(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        runner._model_path = Path("/mock")
        runner._system_prompt = "Old prompt"

        await runner.reset_context("New prompt")
        assert runner._system_prompt == "New prompt"

    async def test_reset_without_prompt(self) -> None:
        runner = VLMRunner()
        runner._loaded = True
        runner._model_path = Path("/mock")
        runner._system_prompt = "Original"

        await runner.reset_context()
        assert runner._system_prompt == "Original"

    async def test_reset_when_not_loaded(self) -> None:
        runner = VLMRunner()
        # Should not raise
        await runner.reset_context("test")
