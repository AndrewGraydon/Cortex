# Project Cortex

**Agentic Local LLM Voice Assistant**

A fully local, privacy-first, voice-and-web AI assistant running on a Raspberry Pi 5 with M5Stack LLM-8850 NPU acceleration. Operates autonomously for safe tasks, requests approval for risky operations, maintains multi-turn conversation history, and keeps all data local by default.

## Hardware Platform

| Component | Role | Specs |
|---|---|---|
| Raspberry Pi 5 (8GB) | Host orchestrator | BCM2712, Debian 12 Bookworm |
| M5Stack LLM-8850 (AX8850) | NPU inference | 24 TOPS INT8, 8GB LPDDR4x |
| PiSugar Whisplay HAT | Voice I/O, LCD, buttons, LEDs | WM8960 codec, ST7789 240x280 LCD |
| PiSugar 3 Plus | Battery / UPS | 5000mAh LiPo, USB-C |

**NPU Models (co-resident, 2,254 MiB / 7,040 MiB = 32% used):**
- **Qwen3-VL-2B** — Vision+language model (~10 tok/s, 1,771 MiB)
- **SenseVoice** — Speech recognition (RTF 0.028, 251 MiB)
- **Kokoro-82M** — Text-to-speech (RTF 0.115, 232 MiB)

## Quick Start

### Development (macOS/Linux — no Pi required)

```bash
# Clone and set up
git clone https://github.com/AndrewGraydon/Cortex.git
cd Cortex
make dev
source .venv/bin/activate

# Run tests (2,224 tests, all pass without hardware)
make test

# Run lint (ruff + mypy strict)
make lint

# Start in mock mode (simulated hardware)
cortex run
```

### On Raspberry Pi

```bash
# Clone and install
git clone https://github.com/AndrewGraydon/Cortex.git
cd Cortex
make dev
source .venv/bin/activate

# Install Pi-specific dependencies
pip install -e ".[pi]"

# Copy and edit config
cp config/cortex.yaml.template config/cortex.yaml

# Run with real hardware
cortex run --no-mock

# Run hardware tests (requires NPU + peripherals)
make test-hw
```

**Prerequisites for Pi:**
- Raspberry Pi OS 64-bit (Debian 12 Bookworm)
- AXCL runtime installed (`sudo apt install axclhost`)
- `axllm` binary compiled from source ([build instructions](docs/guides/phase-0-hardware-setup.md))
- Models downloaded to `~/models/` (SenseVoice, Qwen3-VL-2B, Kokoro)
- See [Phase 0 Setup Guide](docs/guides/phase-0-hardware-setup.md) for detailed hardware setup

### Web UI

Once running, access the web interface at `http://<pi-ip>:8000`:
- **/chat** — WebSocket chat with the assistant (LLM-powered responses)
- **/dashboard** — System health, active timers, notifications
- **/tools** — Manage tools and script-based extensions
- **/settings** — Configuration and security

## Architecture

Seven-layer stack:
1. **HAL** — Hardware abstraction (NPU, audio, display, power) with per-service fallback to mocks
2. **Voice Pipeline** — Button press → ASR → Agent routing → LLM → TTS → Speaker (streaming)
3. **Reasoning Core** — Token-budgeted context assembly (2,047 tokens), multi-turn conversation history
4. **Agent Framework** — Intent routing (regex, zero LLM cost), 5 built-in tools, scheduling, notifications
5. **Security Layer** — 4-tier permissions, audit logging, button-driven approval
6. **Web UI** — FastAPI + HTMX + DaisyUI, bcrypt auth, WebSocket chat
7. **Display UI** — Whisplay LCD status rendering, LED state indicators

### How It Works

```
Button Press → Record Audio → SenseVoice ASR (50ms)
    → Intent Router (regex match? → tool executes directly, no LLM)
    → Context Assembler (history + system prompt + tools → 2,047 tokens)
    → Qwen3-VL-2B inference (~10 tok/s, streaming)
    → Sentence detector → Kokoro TTS (streaming, parallel with LLM)
    → Speaker playback
```

**Key design:** Utility queries ("What time is it?", "Set a timer for 5 minutes") are handled by regex-matched tools with zero LLM cost. Only open-ended queries use the VLM, with full conversation history for multi-turn context.

## Project Structure

```
Cortex/
├── src/cortex/           # Application source
│   ├── core/             # CortexService orchestrator
│   ├── hal/              # Hardware Abstraction Layer
│   │   ├── npu/          # NPU service (mock + AXCL real)
│   │   ├── audio/        # Audio service (mock + ALSA)
│   │   └── display/      # LCD, button, LED services
│   ├── voice/            # Voice pipeline, sentence detector
│   ├── reasoning/        # Context assembler, tool parser, prompts
│   ├── agent/            # Router, processor, tools, scheduling
│   ├── security/         # Permissions, audit, approval
│   ├── memory/           # Memory store, embedding, retrieval
│   ├── web/              # FastAPI app, auth, chat, dashboard
│   ├── iot/              # MQTT, Home Assistant integration
│   ├── external/         # CalDAV, email, notifications
│   └── mcp/              # Model Context Protocol server
├── tests/                # 2,224 unit + integration tests
│   ├── unit/             # Off-Pi tests (run everywhere)
│   ├── integration/      # End-to-end integration tests
│   └── hardware/         # Pi-only NPU + peripheral tests
├── config/               # Configuration templates, systemd units
├── docs/                 # Design docs, setup guides, architecture
├── context/              # AI continuity context files
├── tools/                # Script-based tool extensions
├── models/               # Local model storage (gitignored)
└── data/                 # Runtime data, SQLite DBs (gitignored)
```

## Development

| Command | Description |
|---|---|
| `make dev` | Create venv, install deps, set up pre-commit |
| `make test` | Run unit tests (no Pi required) |
| `make test-hw` | Run hardware tests (Pi only) |
| `make lint` | ruff check + format check + mypy strict |
| `make format` | Auto-format with ruff |
| `make test-cov` | Test coverage report |
| `make clean` | Remove venv, build artifacts |

**CLI commands:**
- `cortex run [--mock/--no-mock]` — Start the voice assistant
- `cortex config` — Show loaded configuration
- `cortex version` — Show version

## Status

- **Phases 0-4 complete** — Hardware, voice pipeline, agent core, web UI, dynamic capabilities
- **2,224 unit + integration tests** passing, ruff + mypy strict clean
- **8/8 NPU hardware tests** passing on Pi (ASR, VLM, TTS, multi-model, full pipeline)
- **End-to-end integration** wired: voice pipeline, web chat, multi-turn context, real HAL services
- **Next:** Phase 5 — IoT integration, Wyoming protocol, proactive intelligence

## Documentation

- [Scope Document](docs/design/scope-v0.1.md) — Full system architecture (v0.1.26)
- [Phase 0 Setup Guide](docs/guides/phase-0-hardware-setup.md) — Hardware assembly and validation
- [Agentic Patterns](docs/architecture/agentic-patterns.md) — Enterprise agentic architecture whitepaper
- [Project Context](context/project-context.md) — AI continuity file for session resumption
- [Config Template](config/cortex.yaml.template) — Full configuration reference

## Design Decisions

53 design decisions tracked (DD-001 through DD-053). Key choices:
- Python 3.11+, Qwen3-VL-2B unified VLM, Kokoro-82M TTS, SenseVoice ASR
- Button-first interaction (no wake word, no VAD)
- Token-budgeted context assembly (P1-P7 priorities, 2,047 token limit)
- Custom in-process action engine (no external workflow engines)
- Script-based tool extensions (TOOL.yaml + scripts/)
- Per-service HAL fallback (real hardware on Pi, mocks elsewhere)

## License

MIT
