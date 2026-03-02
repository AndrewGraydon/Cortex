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
**Phase 0 — Hardware Foundation.** Assembling hardware, installing drivers, running validation tests. No application code yet — all `src/` modules are stubs.

## Architecture
Seven-layer stack (HAL → Voice → Reasoning → Agent → Security → Web UI → Display UI).
See `docs/design/scope-v0.1.md` for full spec.

## Design Decisions (DD-001 through DD-045)
Key choices: Python 3.11+, Qwen3-1.7B primary LLM (7.70 tok/s measured), Kokoro-82M TTS,
SenseVoice ASR, FastVLM-0.5B VLM (DD-045), FastAPI backend, SQLite + sqlite-vec, ZeroMQ IPC,
bubblewrap sandbox, systemd services. LCD display adapted from PiSugar whisplay-ai-chatbot
(Pillow + cairosvg + SPI). Web UI framework deferred to Phase 3.

## Related Repositories
- **Kokoro TTS on LLM-8850:** https://github.com/AndrewGraydon/kokoro.LM8850
- **Whisplay reference chatbot:** https://github.com/PiSugar/whisplay-ai-chatbot

## Tech Stack
- Python 3.11+, FastAPI, ZeroMQ, SQLite, Pillow, cairosvg, NumPy
- AXCL runtime for NPU inference
- sherpa-onnx for ASR with AXCL backend
- Debian 12 Bookworm on Raspberry Pi OS

## Code Style
- Linter: ruff (target Python 3.11, 100-char line length)
- Type checking: mypy (strict mode)
- Tests: pytest with pytest-asyncio
- Logging: structlog (structured JSON)

## Conventions
- Update `context/project-context.md` when making significant design decisions
- Design decisions use IDs: DD-NNN with date and rationale
- Scope doc version bumps on changes (currently v0.1.15)
- Hardware metrics go in `docs/guides/phase-0-hardware-setup.md` completion checklist
- Models stored in `models/` (gitignored), runtime data in `data/` (gitignored)
- No secrets in config files — use `.env` (gitignored)

## Hardware Constraints (keep in mind)
- NPU memory: 8GB total, 7040 MiB usable. Measured model budget: ~4.95GB (29.7% headroom)
- PCIe 2.0 x1 to NPU: ~500 MB/s — minimize host↔NPU transfers
- Combined power ~19W — mains power required for NPU inference
- PiSugar AUTO switch must be disabled (I2C conflict with Whisplay)
