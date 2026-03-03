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
**Phase 2 — Agent Core — COMPLETE.** All milestones done, 487 unit + integration tests passing.
Hybrid intent router, 4-tier permissions, audit log, tool calling, memory, scheduling, notifications, health monitor.
Validated on Pi (497 pass including hardware tests, 7 expected HW failures).
Next: Phase 3 — Web UI (FastAPI + HTMX/Svelte, auth, external services, A2A).

## Architecture
Seven-layer stack (HAL → Voice → Reasoning → Agent → Security → Web UI → Display UI).
See `docs/design/scope-v0.1.md` for full spec.

## Design Decisions (DD-001 through DD-050)
Key choices: Python 3.11+, Qwen3-1.7B primary LLM (7.70 tok/s measured), Kokoro-82M TTS,
SenseVoice ASR, FastVLM-0.5B VLM (DD-045), FastAPI backend, SQLite + sqlite-vec, ZeroMQ IPC,
bubblewrap sandbox, systemd services. Audio via ALSA `default` device (DD-049, NOT hw:0,0).
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
- Tests: pytest with pytest-asyncio (487 tests passing)
- Logging: structlog (structured JSON)
- All HAL interfaces via Protocol classes in `hal/protocols.py`

## Conventions
- Update `context/project-context.md` when making significant design decisions
- Design decisions use IDs: DD-NNN with date and rationale
- Scope doc version bumps on changes (currently v0.1.20)
- Hardware metrics go in `docs/guides/phase-0-hardware-setup.md` completion checklist
- Models stored in `models/` (gitignored), runtime data in `data/` (gitignored)
- No secrets in config files — use `.env` (gitignored)

## Hardware Constraints (keep in mind)
- NPU memory: 8GB total, 7040 MiB usable. Measured model budget: ~4.95GB (29.7% headroom)
- PCIe 2.0 x1 to NPU: ~500 MB/s — minimize host↔NPU transfers
- Combined power ~19W — mains power required for NPU inference
- PiSugar AUTO switch must be disabled (I2C conflict with Whisplay)
