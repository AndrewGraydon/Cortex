"""LLM runner — wraps Qwen3 C++ API binary + tokenizer HTTP server.

Architecture (DD-046):
  Cortex LLMRunner
    ├── Subprocess: python3 qwen3_tokenizer_uid.py (port 12345)
    └── Subprocess: ./main_api_axcl_aarch64 (port 8000, ax-llm HTTP API)

The C++ binary handles all NPU operations. We communicate via HTTP.
The tokenizer server is required by the C++ binary (internal RPC).

API format (old ax-llm binary, pre-OpenAI-compat):
  POST /api/chat     — synchronous chat, returns {"done":true,"message":"..."}
  POST /api/generate — async generation, poll via GET /api/generate_provider
  POST /api/reset    — reset conversation context
  POST /api/stop     — stop in-progress generation
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from cortex.hal.types import InferenceInputs, InferenceOutputs

logger = logging.getLogger(__name__)

# Default ports for LLM subprocesses
DEFAULT_API_PORT = 8000
DEFAULT_TOKENIZER_PORT = 12345

# Streaming poll interval (seconds)
STREAM_POLL_INTERVAL = 0.15

# Model-specific constants
QWEN3_AXMODEL_NUM = 28
QWEN3_TOKENS_EMBED_NUM = 151936
QWEN3_TOKENS_EMBED_SIZE = 2048


class LLMRunner:
    """Qwen3 LLM via C++ API binary subprocess.

    Starts two subprocesses:
    1. Tokenizer HTTP server (Python, port 12345)
    2. LLM API server (C++, port 8000)

    Communication is via HTTP.
    Non-streaming: POST /api/chat (blocks until done).
    Streaming: POST /api/generate + poll GET /api/generate_provider.
    """

    def __init__(self) -> None:
        self._tokenizer_proc: asyncio.subprocess.Process | None = None
        self._api_proc: asyncio.subprocess.Process | None = None
        self._client: httpx.AsyncClient | None = None
        self._loaded = False
        self._memory_mb = 0
        self._api_port = DEFAULT_API_PORT
        self._tokenizer_port = DEFAULT_TOKENIZER_PORT
        self._model_path: Path | None = None

    @property
    def model_type(self) -> str:
        return "llm"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def memory_mb(self) -> int:
        return self._memory_mb

    async def load(self, model_path: Path, config: dict[str, Any]) -> None:
        """Start tokenizer server and LLM API binary.

        Args:
            model_path: Path to model directory (e.g., ~/models/Qwen3-1.7B)
            config: Configuration dict with optional overrides:
                - api_port: HTTP API port (default 8000)
                - tokenizer_port: Tokenizer server port (default 12345)
                - system_prompt: System prompt for the LLM
                - memory_mb: NPU memory in MB (default 3375)
                - venv_python: Path to Python with transformers (for tokenizer)
        """
        if self._loaded:
            msg = "LLM already loaded"
            raise RuntimeError(msg)

        self._model_path = model_path
        self._api_port = config.get("api_port", DEFAULT_API_PORT)
        self._tokenizer_port = config.get("tokenizer_port", DEFAULT_TOKENIZER_PORT)
        self._memory_mb = config.get("memory_mb", 3375)
        system_prompt = config.get("system_prompt", "You are a helpful assistant.")
        venv_python = config.get("venv_python", "python3")

        try:
            await self._start_tokenizer(model_path, venv_python)
            await self._start_api_binary(model_path, system_prompt)
            self._client = httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{self._api_port}",
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
            self._loaded = True
            logger.info("LLM loaded: %s (port %d)", model_path.name, self._api_port)
        except Exception:
            await self.unload()
            raise

    async def unload(self) -> None:
        """Stop subprocesses and free resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

        for name, proc_attr in [("API", "_api_proc"), ("tokenizer", "_tokenizer_proc")]:
            proc: asyncio.subprocess.Process | None = getattr(self, proc_attr)
            if proc and proc.returncode is None:
                logger.info("Stopping LLM %s subprocess (pid %d)", name, proc.pid)
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            setattr(self, proc_attr, None)

        self._loaded = False
        self._memory_mb = 0

    async def infer(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Send prompt, get full response via POST /api/chat."""
        self._check_loaded()
        assert self._client is not None

        prompt = str(inputs.data) if inputs.data is not None else ""
        body = self._build_chat_request(prompt, inputs.params)

        resp = await self._client.post("/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()

        content = data.get("message", "")
        content = self._strip_think_tags(content)

        return InferenceOutputs(
            data=content,
            metadata={
                "finish_reason": "stop" if data.get("done") else "length",
            },
        )

    async def infer_stream(self, inputs: InferenceInputs) -> AsyncIterator[InferenceOutputs]:
        """Stream tokens via POST /api/generate + polling /api/generate_provider."""
        self._check_loaded()
        assert self._client is not None

        prompt = str(inputs.data) if inputs.data is not None else ""
        body = self._build_generate_request(prompt, inputs.params)

        # Start async generation
        resp = await self._client.post("/api/generate", json=body)
        resp.raise_for_status()

        # Poll for incremental deltas
        buffer = ""
        while True:
            await asyncio.sleep(STREAM_POLL_INTERVAL)
            poll_resp = await self._client.get("/api/generate_provider")
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            delta = poll_data.get("response", "")
            done = poll_data.get("done", False)

            if delta:
                buffer += delta
                clean = self._strip_think_tags(buffer)
                prev_clean = self._strip_think_tags(buffer[: -len(delta)])
                new_text = clean[len(prev_clean) :]
                if new_text:
                    yield InferenceOutputs(
                        data=new_text,
                        metadata={
                            "is_final": done,
                            "finish_reason": "stop" if done else None,
                        },
                    )

            if done:
                break

    async def reset_context(self, system_prompt: str | None = None) -> None:
        """Reset LLM KV cache context via POST /api/reset."""
        self._check_loaded()
        assert self._client is not None

        body: dict[str, Any] = {}
        if system_prompt:
            body["system_prompt"] = system_prompt

        resp = await self._client.post("/api/reset", json=body)
        resp.raise_for_status()
        logger.info("LLM context reset")

    # --- Internal helpers ---

    def _check_loaded(self) -> None:
        if not self._loaded:
            msg = "LLM not loaded"
            raise RuntimeError(msg)

    def _build_chat_request(
        self, prompt: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Build request for POST /api/chat (synchronous, messages array)."""
        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
        }
        self._add_sampling_params(body, params)
        return body

    def _build_generate_request(
        self, prompt: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Build request for POST /api/generate (async, prompt string)."""
        body: dict[str, Any] = {
            "prompt": prompt,
        }
        self._add_sampling_params(body, params)
        return body

    @staticmethod
    def _add_sampling_params(body: dict[str, Any], params: dict[str, Any]) -> None:
        """Add sampling parameters to request body."""
        if "temperature" in params:
            body["temperature"] = params["temperature"]
        if "top_p" in params:
            body["top-p"] = params["top_p"]
        if "top_k" in params:
            body["top-k"] = params["top_k"]
        if "repetition_penalty" in params:
            body["repetition_penalty"] = params["repetition_penalty"]

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Remove Qwen3 thinking tags from output."""
        import re

        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    async def _start_tokenizer(self, model_path: Path, venv_python: str) -> None:
        """Start tokenizer HTTP server subprocess, or detect existing one.

        If a tokenizer is already running on the configured port (e.g. started
        manually via nohup), skip subprocess creation and reuse it.
        """
        tokenizer_url = f"http://127.0.0.1:{self._tokenizer_port}/get_uid"

        # Probe for an already-running tokenizer server.
        # Use sync httpx — the tokenizer's http.server doesn't handle async well.
        def _probe_tokenizer() -> bool:
            try:
                resp = httpx.get(tokenizer_url, timeout=3.0)
                return resp.status_code < 500
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                return False

        loop = asyncio.get_event_loop()
        if await loop.run_in_executor(None, _probe_tokenizer):
            logger.info(
                "Tokenizer already running on port %d, reusing",
                self._tokenizer_port,
            )
            return

        tokenizer_script = model_path / "qwen3_tokenizer_uid.py"
        if not tokenizer_script.exists():
            msg = f"Tokenizer script not found: {tokenizer_script}"
            raise FileNotFoundError(msg)

        self._tokenizer_proc = await asyncio.create_subprocess_exec(
            venv_python,
            str(tokenizer_script),
            "--host",
            "127.0.0.1",
            "--port",
            str(self._tokenizer_port),
            cwd=str(model_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "Tokenizer server starting (pid %d, port %d)",
            self._tokenizer_proc.pid,
            self._tokenizer_port,
        )

        await self._wait_for_http(
            tokenizer_url,
            timeout=30.0,
            name="tokenizer",
        )

    async def _start_api_binary(self, model_path: Path, system_prompt: str) -> None:
        """Start LLM API binary subprocess."""
        # Find the binary
        binary = model_path / "main_api_axcl_aarch64"
        if not binary.exists():
            msg = f"LLM API binary not found: {binary}"
            raise FileNotFoundError(msg)

        # Find model files
        axmodel_dir = None
        for candidate in model_path.iterdir():
            if candidate.is_dir() and candidate.name.startswith("qwen3"):
                axmodel_dir = candidate
                break
        if axmodel_dir is None:
            msg = f"No qwen3 axmodel directory found in {model_path}"
            raise FileNotFoundError(msg)

        rel_dir = axmodel_dir.name
        template = f"{rel_dir}/qwen3_p128_l%d_together.axmodel"
        post_model = f"{rel_dir}/qwen3_post.axmodel"
        embed_file = f"{rel_dir}/model.embed_tokens.weight.bfloat16.bin"

        cmd = [
            str(binary),
            "--template_filename_axmodel",
            template,
            "--axmodel_num",
            str(QWEN3_AXMODEL_NUM),
            "--url_tokenizer_model",
            f"http://127.0.0.1:{self._tokenizer_port}",
            "--filename_post_axmodel",
            post_model,
            "--filename_tokens_embed",
            embed_file,
            "--tokens_embed_num",
            str(QWEN3_TOKENS_EMBED_NUM),
            "--tokens_embed_size",
            str(QWEN3_TOKENS_EMBED_SIZE),
            "--use_mmap_load_embed",
            "1",
            "--system_prompt",
            system_prompt,
            "--devices",
            "0",
        ]

        self._api_proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(model_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "LLM API binary starting (pid %d, port %d)",
            self._api_proc.pid,
            self._api_port,
        )

        # Health check: POST /api/reset returns {"status":"ok"} when ready.
        # Use POST (not GET) because the old binary has no GET health endpoint.
        await self._wait_for_ready(
            f"http://127.0.0.1:{self._api_port}/api/reset",
            timeout=120.0,
            name="LLM API",
        )

    @staticmethod
    async def _wait_for_http(url: str, timeout: float, name: str) -> None:
        """Poll HTTP GET endpoint until it responds or timeout."""
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    resp = await client.get(url, timeout=2.0)
                    if resp.status_code < 500:
                        logger.info("%s ready at %s", name, url)
                        return
                except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                    pass
                await asyncio.sleep(0.5)

        msg = f"{name} failed to start within {timeout}s at {url}"
        raise TimeoutError(msg)

    @staticmethod
    async def _wait_for_ready(url: str, timeout: float, name: str) -> None:
        """Poll HTTP POST endpoint until it responds or timeout.

        The old ax-llm binary has no GET health endpoint; POST /api/reset
        returns {"status":"ok"} when the model is loaded and ready.
        It returns {"error":"Model initing"} while still loading.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    resp = await client.post(
                        url, json={}, timeout=2.0,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code < 500:
                        data = resp.json()
                        if data.get("status") == "ok":
                            logger.info("%s ready at %s", name, url)
                            return
                        # "Model initing" — still loading, keep polling
                        logger.debug("%s still loading: %s", name, data)
                except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                    pass
                await asyncio.sleep(1.0)

        msg = f"{name} failed to start within {timeout}s at {url}"
        raise TimeoutError(msg)
