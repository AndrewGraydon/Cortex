# Hardware Research Notes
# Compiled: 2026-02-27 (updated Session 2)

## M5Stack LLM-8850 (AX8850)

### Specifications
- SoC: Axera AX8850
- NPU: 24 TOPS @ INT8
- CPU: Octa-core Cortex-A55 @ 1.7 GHz (on the NPU card itself)
- Memory: 8GB LPDDR4x, 64-bit, 4266 Mbps
- Storage: 32 Mbit SPI NOR Flash (bootloader only)
- Video: 8K@30fps H.264/H.265 encode, 8K@60fps decode, 16-ch 1080p parallel decode
- Security: AES/DES/3DES/SHA-256 hardware security module
- Form factor: M.2 M-Key 2242
- Interface: PCIe 2.0 x2 (backward compatible x1 for RPi)
- Power: 7W @ 3.3V max
- Cooling: Onboard turbo fan + CNC aluminum heatsink, EC-controlled
- Operating temp: 0-60°C
- Weight: 14.7g
- Dimensions: 42.6 x 24.0 x 9.7 mm

### Software
- OS support: Ubuntu 20.04/22.04/24.04, Debian 12 (NO Windows/macOS/WSL)
- Runtime: AXCL with C and Python APIs
- Driver: axcl-smi (apt package from M5Stack repo)
- Model framework: Native AXCL for optimized models, sherpa-onnx for ASR
- Model format: .axmodel (converted via Pulsar2 toolchain)

### Key Findings
- Pi 5 connects via PCIe 2.0 x1 (~500 MB/s)
- Cannot share PCIe bus with NVMe SSD
- M5Stack PiHat Kit requires ≥27W USB-C PD, powers both NPU and Pi
- RPi M.2 HAT+ also works, powered via Pi's USB-C (5V@5A)
- NPU has its own 8-core CPU — runs inference independently
- CMM (Compute Memory) is the NPU's memory pool, ~7040 MiB usable
- AXCL-SMI shows: Memory-Usage (system) and CMM-Usage (models/compute)
- User reviews report ~20 tok/s for smaller models, one noted TOPS rating feels inflated
- Pulsar2 toolchain can convert custom ONNX models to axmodel format

### Performance Benchmarks (from wiki/reviews)
- Qwen3-0.6B (w8a16): 12.88 tok/s
- Qwen2.5-1.5B-Instruct: 15.03 tok/s
- Qwen2.5-VL-3B (image inference): 4.81 tok/s
- SenseVoice (7s audio): RTF 0.015 (0.105s processing time)
- Competitor: RPi AI HAT+ 2 gets 6.74 tok/s on same Qwen2.5-1.5B

### Important Warnings
- Do NOT use PD adapters with bare M.2 card (use non-PD 5V@3A)
- M5Stack PiHat Kit REQUIRES PD adapter (≥9V@3A)
- Device gets hot under load — do not touch during operation
- Third-party M.2 adapters may have compatibility issues
- Waveshare PCIe-to-dual-lane adapter confirmed NOT supported

## PiSugar Whisplay HAT

### Specifications
- Display: 1.69" IPS LCD, 240x280 pixels (ST7789 controller)
- Audio codec: WM8960
- Microphones: Dual MEMS mics
- Speaker: Built-in mono, supports external via XH2.0 connector
- LEDs: RGB indicator lights
- Buttons: Programmable push buttons
- Interfaces: I2C (audio), SPI (LCD), I2S (audio)
- Compatible: RPi Zero/Zero 2 W/RPi 5

### Software
- Driver: install_wm8960_drive.sh from GitHub repo
- Python library: whisplay.py (auto-detects platform)
- GitHub: https://github.com/PiSugar/Whisplay
- Reference chatbot: https://github.com/PiSugar/whisplay-ai-chatbot

### Key Findings
- LCD is glass — fragile, handle by PCB edges
- Button side aligns with Pi's USB port side
- On RPi OS 2025-11-24+, new sound cards NOT set as default
- Must specify card number explicitly in ALSA commands
- If using with PiSugar 3 Plus, disable AUTO switch to prevent I2C conflicts
- External speaker: mono only, XH2.0 connector
- Test suite included: run_test.sh (LCD, buttons, LEDs, audio)

## PiSugar 3 Plus

### Specifications
- Battery: 5000mAh LiPo (magnetic attach)
- Output: 5V @ 2.5-3A max
- Input: 5V @ 3A max (USB-C or Micro-USB)
- RTC: DS3231-compatible, >1 year standby
- MCU: Independent power management
- I2C addresses: 0x57 (EEPROM), 0x68 (RTC), 0x75 (MCU)
- Connection: Pogo pins (back of Pi) — does NOT occupy GPIO
- Features: UPS, soft shutdown, watchdog, custom button, OTA firmware
- Web UI: http://<ip>:8421

### Software
- Power manager: pisugar-power-manager (Rust + Vue2.0)
- Install: wget + bash script from cdn.pisugar.com
- API: UDP/UDS/WebSocket (e.g., `echo "get battery" | nc -U /tmp/pisugar-server.sock`)
- Status: Battery %, charging state, voltage, external power detection

### Key Findings
- Max 3A output is insufficient for Pi 5 + NPU at full load (~4A+ needed)
- Viable as UPS and for portable light-duty use
- Pi 5 under-voltage warnings likely when running NPU on battery
- Anti-mistaken-touch enabled by default (click & hold to power on)
- RTC can be used for reliable audit timestamps
- Watchdog can auto-restart crashed Pi
- I2C address configurable to avoid conflicts

## Kokoro-82M TTS (Selected — DD-011)

### Specifications
- Architecture: StyleTTS 2 + ISTFTNet vocoder, decoder-only
- Parameters: 82 million
- Developer: hexgrad (open-weight, Apache 2.0 license)
- Latest: v1.0 (2025-01-27), v1.1-zh (2025-02-26)
- Voices: 54 across 8 languages (v1.0)
- Output: 24,000 Hz sample rate
- HuggingFace rank: #1 TTS Spaces Arena (single-speaker), #2 overall

### AX8850 NPU Deployment
- Hybrid pipeline: 3 axmodel parts on NPU + ONNX vocoder on CPU
- CMM memory: 237 MB (fixed, regardless of language)
- OS memory: 23 MB (English), 233 MB (Chinese)
- RTF: 0.067 (15x faster than real-time)
- Init time: ~5.1 seconds (one-time, mitigated by persistent HTTP server)
- Max token length per chunk: 96 tokens (axmodel constraint)
- Official AXERA-TECH repo: https://huggingface.co/AXERA-TECH/kokoro.axera
- Custom LLM-8850 implementation: https://github.com/AndrewGraydon/kokoro.LM8850

### Performance on AX8850
- Model1 (NPU): 22.1 ms avg
- Model2 (NPU): 17.4 ms avg
- Model3 (NPU): 185.3 ms avg
- Model4 (ONNX/CPU vocoder): 73.7 ms avg
- Total for 4.8s audio: ~322 ms

### Comparison to MeloTTS (rejected)
- Kokoro RTF 0.067 vs MeloTTS RTF 0.125 (2x faster)
- Kokoro 237 MB NPU vs MeloTTS ~44 MB NPU (Kokoro uses more NPU but less than originally estimated 800MB)
- Kokoro ranked #1 TTS quality vs MeloTTS mid-tier by 2026 standards
- MeloTTS last release March 2024 (stale) vs Kokoro actively maintained
- MeloTTS encoder still on CPU (not fully offloaded); Kokoro 3/4 stages on NPU

### Languages (v1.0)
- American English (a), British English (b), Spanish (e), French (f)
- Hindi (h), Italian (i), Japanese (j), Mandarin Chinese (z)
- AXCL axmodel currently supports: English, Chinese, Japanese

### Known Limitations
- No voice cloning (voice blending only)
- 96-token max per chunk on axmodel — must sentence-split longer text
- espeak-ng G2P can produce pronunciation errors on proper nouns
- Training data primarily narration/reading — conversational speech slightly less natural
- CPU-only on Pi is slower than real-time (NPU essential)
