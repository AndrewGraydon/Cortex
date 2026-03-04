# Project Cortex — Claude Code Instructions

## Project Overview
Agentic local LLM voice assistant on Raspberry Pi 5 with M5Stack LLM-8850 NPU.
Privacy-first, local-first, with optional secure external access.

## Key Files
- **Design scope:** `docs/design/scope-v0.1.md` (primary architecture doc)
- **Phase 0 guide:** `docs/guides/phase-0-hardware-setup.md`
- **AI context file:** `context/project-context.md` (feed to new sessions for continuity)
- **Hardware research:** `context/hardware-research.md`
- **Config template:** `config/cortex.yaml.template`

## Current Phase
**Phase 3a — Web Foundation — COMPLETE.** 7 milestones, 736 unit + integration tests passing.
FastAPI + HTMX + DaisyUI, bcrypt auth, WebSocket chat, dashboard, approvals, notifications, tools, settings.
All NPU hardware tests passing on Pi (7/7: ASR, LLM, TTS, multi-model, full pipeline).
Next: Phase 3b — External services (CalDAV, IMAP, ntfy), MCP server, A2A protocol.

## Architecture
Seven-layer stack (HAL → Voice → Reasoning → Agent → Security → Web UI → Display UI).
See `docs/design/scope-v0.1.md` for full spec.

## Design Decisions (DD-001 through DD-051)
Key choices: Python 3.11+, Qwen3-VL-2B unified VLM (14.1 tok/s, DD-051), Kokoro-82M TTS,
SenseVoice ASR, FastAPI backend, SQLite + sqlite-vec, ZeroMQ IPC, bubblewrap sandbox,
systemd services. Audio via ALSA `default` device (DD-049, NOT hw:0,0).
VLM via axllm serve (OpenAI-compat API, SSE streaming, no separate tokenizer server).
LCD display adapted from PiSugar whisplay-ai-chatbot (Pillow + cairosvg + SPI).
Script-based tools with progressive disclosure (DD-050) — TOOL.yaml + scripts/ folders as
alternative to Python handler classes, inspired by Anthropic's Claude Skills architecture.

## Related Repositories
- **Kokoro TTS on LLM-8850:** https://github.com/AndrewGraydon/kokoro.LM8850
- **Whisplay reference chatbot:** https://github.com/PiSugar/whisplay-ai-chatbot

## Tech Stack
- Python 3.11+, FastAPI, ZeroMQ, SQLite, Pillow, cairosvg, NumPy
- AXCL runtime + pyaxengine for NPU inference
- SenseVoice ASR via pyaxengine (not sherpa-onnx)
- Debian 12 Bookworm on Raspberry Pi OS

## Development
- `make dev` — create venv, install deps, set up pre-commit
- `make lint` — ruff check + format check + mypy
- `make test` — run unit tests (no Pi needed)
- `make test-hw` — run hardware tests (Pi only)
- CLI: `cortex run`, `cortex config`, `cortex version`

## Code Style
- Linter: ruff (target Python 3.11, 100-char line length)
- Type checking: mypy (strict mode)
- Tests: pytest with pytest-asyncio (765 tests passing)
- Logging: structlog (structured JSON)
- All HAL interfaces via Protocol classes in `hal/protocols.py`

## Conventions
- Update `context/project-context.md` when making significant design decisions
- Design decisions use IDs: DD-NNN with date and rationale
- Scope doc version bumps on changes (currently v0.1.22)
- Hardware metrics go in `docs/guides/phase-0-hardware-setup.md` completion checklist
- Models stored in `models/` (gitignored), runtime data in `data/` (gitignored)
- No secrets in config files — use `.env` (gitignored)

## Hardware Constraints (keep in mind)
- NPU memory: 8GB total, 7040 MiB usable. Model budget: 3,043 MiB (43% used, 56.8% headroom)
- PCIe 2.0 x1 to NPU: ~500 MB/s — minimize host↔NPU transfers
- Combined power ~19W — mains power required for NPU inference
- PiSugar AUTO switch must be disabled (I2C conflict with Whisplay)
