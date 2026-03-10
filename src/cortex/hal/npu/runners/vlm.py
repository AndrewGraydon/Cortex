"""VLM runner — wraps Qwen3-VL-2B via axllm serve (OpenAI-compatible API).

Architecture (DD-051):
  Cortex VLMRunner
    └── Subprocess: axllm serve <model_dir> (port 8080, OpenAI-compat API)

The axllm binary handles all NPU operations including the integrated tokenizer
and image encoder. Communication is via HTTP with SSE streaming.

Prerequisites:
  - axllm binary: compiled from source (axllm branch of AXERA-TECH/ax-llm)
  - config.json: must exist in model_dir with tokenizer_type, axmodel paths, etc.
  - See docs/guides/phase-0-hardware-setup.md §0.8 for build instructions.

API format (new axllm binary, OpenAI-compatible):
  POST /v1/chat/completions — chat completion with optional vision (images)
  GET  /v1/models           — list loaded models (health check)

Replaces both old Qwen3-1.7B text-only LLM and FastVLM-0.5B stub.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from cortex.hal.types import InferenceInputs, InferenceOutputs

logger = logging.getLogger(__name__)

# Default port for axllm serve (axllm defaults to 8080)
DEFAULT_API_PORT = 8080

# SSE streaming timeout (seconds per token — generous for slow generation)
SSE_READ_TIMEOUT = 120.0


class VLMRunner:
    """Qwen3-VL-2B via axllm serve subprocess.

    Starts a single subprocess: axllm serve <model_dir>
    Supports both text-only and vision (image+text) inference.
    Uses OpenAI-compatible /v1/chat/completions with SSE streaming.
    """

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._client: httpx.AsyncClient | None = None
        self._loaded = False
        self._memory_mb = 0
        self._api_port = DEFAULT_API_PORT
        self._model_path: Path | None = None
        self._system_prompt: str = ""
        self._model_name: str = "default"

    @property
    def model_type(self) -> str:
        return "vlm"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def memory_mb(self) -> int:
        return self._memory_mb

    async def load(self, model_path: Path, config: dict[str, Any]) -> None:
        """Start axllm serve subprocess.

        Args:
            model_path: Path to model directory containing config.json and axllm binary.
                The model dir must have a config.json with tokenizer_type, axmodel
                template paths, and embedding configuration. See Phase 0 guide.
            config: Configuration dict with optional overrides:
                - api_port: HTTP API port (default 8080)
                - memory_mb: NPU memory in MB (default 1771, measured on hardware)
                - system_prompt: System prompt for the LLM
                - axllm_binary: Path to axllm binary (default: search model dir)
        """
        if self._loaded:
            msg = "VLM already loaded"
            raise RuntimeError(msg)

        self._model_path = model_path
        self._api_port = config.get("api_port", DEFAULT_API_PORT)
        self._memory_mb = config.get("memory_mb", 1771)
        self._system_prompt = config.get("system_prompt", "You are a helpful assistant.")

        try:
            await self._start_axllm(model_path, config)
            self._client = httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{self._api_port}",
                timeout=httpx.Timeout(SSE_READ_TIMEOUT, connect=10.0),
            )
            self._loaded = True
            logger.info("VLM loaded: %s (port %d)", model_path.name, self._api_port)
        except Exception:
            await self.unload()
            raise

    async def unload(self) -> None:
        """Stop subprocess and free resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

        if self._proc and self._proc.returncode is None:
            logger.info("Stopping axllm subprocess (pid %d)", self._proc.pid)
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._proc = None

        # Brief delay for OS to release the port before any restart
        await asyncio.sleep(0.5)

        self._loaded = False
        self._memory_mb = 0

    async def infer(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Send prompt, get full response via POST /v1/chat/completions."""
        self._check_loaded()
        assert self._client is not None

        prompt = str(inputs.data) if inputs.data is not None else ""
        messages = self._build_messages(prompt, inputs.params)
        body = self._build_request_body(messages, inputs.params, stream=False)

        resp = await self._client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"]["content"]
        content = self._strip_think_tags(content)
        finish_reason = data["choices"][0].get("finish_reason", "stop")

        return InferenceOutputs(
            data=content,
            metadata={"finish_reason": finish_reason},
        )

    async def infer_stream(self, inputs: InferenceInputs) -> AsyncIterator[InferenceOutputs]:
        """Stream tokens via POST /v1/chat/completions with SSE."""
        self._check_loaded()
        assert self._client is not None

        prompt = str(inputs.data) if inputs.data is not None else ""
        messages = self._build_messages(prompt, inputs.params)
        body = self._build_request_body(messages, inputs.params, stream=True)

        async with self._client.stream("POST", "/v1/chat/completions", json=body) as resp:
            resp.raise_for_status()
            buffer = ""
            emitted_len = 0
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break

                chunk = json.loads(payload)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                finish_reason = chunk["choices"][0].get("finish_reason")

                if content:
                    buffer += content
                    safe = self._safe_clean(buffer)
                    new_text = safe[emitted_len:]
                    emitted_len = len(safe)
                    if new_text:
                        done = finish_reason is not None
                        yield InferenceOutputs(
                            data=new_text,
                            metadata={
                                "is_final": done,
                                "finish_reason": finish_reason,
                            },
                        )

    async def reset_context(self, system_prompt: str | None = None) -> None:
        """Reset conversation context.

        The axllm binary manages context internally per session.
        For a clean reset, we restart the subprocess.
        """
        if system_prompt:
            self._system_prompt = system_prompt

        if not self._loaded or self._model_path is None:
            return

        # axllm doesn't expose a context reset endpoint.
        # For now, log the request — context resets naturally at token limit.
        logger.info("VLM context reset requested (system_prompt updated)")

    # --- Internal helpers ---

    def _check_loaded(self) -> None:
        if not self._loaded:
            msg = "VLM not loaded"
            raise RuntimeError(msg)

    def _build_messages(self, prompt: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Build OpenAI-format messages array.

        Supports three input modes:
        1. Pre-built messages: pass params["messages"] for multi-turn context
        2. Vision: pass params["image_base64"] for image+text
        3. Text-only: default, builds [system, user] from prompt string
        """
        # Pre-built messages passthrough (multi-turn context from pipeline)
        if "messages" in params:
            pre_built = list(params["messages"])
            # Ensure system prompt is present as first message
            if pre_built and pre_built[0].get("role") != "system" and self._system_prompt:
                pre_built.insert(0, {"role": "system", "content": self._system_prompt})
            return pre_built

        messages: list[dict[str, Any]] = []

        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        # Check for vision input (image in params)
        image_b64 = params.get("image_base64")
        if image_b64:
            # Multimodal message with image + text
            content: list[dict[str, Any]] = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                },
                {"type": "text", "text": prompt},
            ]
            messages.append({"role": "user", "content": content})
        else:
            # Text-only message
            messages.append({"role": "user", "content": prompt})

        return messages

    def _build_request_body(
        self,
        messages: list[dict[str, Any]],
        params: dict[str, Any],
        *,
        stream: bool,
    ) -> dict[str, Any]:
        """Build OpenAI-format request body."""
        body: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "stream": stream,
        }
        if "temperature" in params:
            body["temperature"] = params["temperature"]
        if "top_p" in params:
            body["top_p"] = params["top_p"]
        if "max_tokens" in params:
            body["max_tokens"] = params["max_tokens"]
        if "repetition_penalty" in params:
            body["repetition_penalty"] = params["repetition_penalty"]
        return body

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Remove Qwen3 thinking tags from complete output."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _safe_clean(text: str) -> str:
        """Strip complete think tags, hold back incomplete ones.

        For streaming: returns only text that is safe to emit.
        Incomplete ``<think>`` blocks (opening without closing) are held back.
        """
        # Strip all complete <think>...</think> pairs
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # Truncate at any remaining incomplete <think> tag
        idx = cleaned.find("<think>")
        if idx != -1:
            cleaned = cleaned[:idx]
        return cleaned

    async def _start_axllm(self, model_path: Path, config: dict[str, Any]) -> None:
        """Start axllm serve subprocess."""
        binary = self._find_binary(model_path, config)

        cmd = [
            str(binary),
            "serve",
            str(model_path),
            "--port",
            str(self._api_port),
        ]

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "axllm serve starting (pid %d, port %d)",
            self._proc.pid,
            self._api_port,
        )

        await self._wait_for_ready(
            f"http://127.0.0.1:{self._api_port}",
            timeout=180.0,
        )

    @staticmethod
    def _find_binary(model_path: Path, config: dict[str, Any]) -> Path:
        """Find axllm binary — config override, model dir, or PATH."""
        # Config override
        if "axllm_binary" in config:
            binary = Path(config["axllm_binary"])
            if binary.exists():
                return binary
            msg = f"axllm binary not found at configured path: {binary}"
            raise FileNotFoundError(msg)

        # Look in model directory
        for name in ("axllm", "axllm_aarch64"):
            candidate = model_path / name
            if candidate.exists():
                return candidate

        # Look in PATH via /usr/bin or /usr/local/bin
        import shutil

        path_binary = shutil.which("axllm")
        if path_binary:
            return Path(path_binary)

        msg = f"axllm binary not found in {model_path} or PATH"
        raise FileNotFoundError(msg)

    async def _wait_for_ready(self, base_url: str, timeout: float) -> None:
        """Poll GET /v1/models until the server is ready.

        Also captures the model name from the response for use in API requests.
        Detects subprocess crashes early to avoid waiting the full timeout.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        url = f"{base_url}/v1/models"

        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                # Detect subprocess crash — fail fast with stderr
                if self._proc and self._proc.returncode is not None:
                    stderr = ""
                    if self._proc.stderr:
                        stderr_bytes = await self._proc.stderr.read()
                        stderr = stderr_bytes.decode(errors="replace")[-500:]
                    msg = f"axllm exited with code {self._proc.returncode}: {stderr}"
                    raise RuntimeError(msg)

                try:
                    resp = await client.get(url, timeout=2.0)
                    if resp.status_code == 200:
                        # Extract model name from response
                        data = resp.json()
                        models = data.get("data", [])
                        if models:
                            self._model_name = models[0].get("id", "default")
                        logger.info("axllm ready at %s (model: %s)", base_url, self._model_name)
                        return
                except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                    pass
                await asyncio.sleep(1.0)

        msg = f"axllm failed to start within {timeout}s at {base_url}"
        raise TimeoutError(msg)
