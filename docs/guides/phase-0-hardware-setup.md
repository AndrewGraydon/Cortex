# Project Cortex — Phase 0: Hardware Foundation Setup Guide

## Goal
Get all hardware assembled, verified, and communicating. Establish the base OS, driver stack, and confirm there are no bus conflicts between components. Profile actual power and memory budgets.

---

## 0.1 Prerequisites & Important Warnings

### Power Architecture (CRITICAL)

```
                  ┌──────────────────────┐
  USB-C PD ──────►│  M5Stack PiHat OR    │──── 3.3V ──►  LLM-8850 NPU
  (27W min)       │  RPi M.2 HAT+       │──── 5V ────►  Raspberry Pi 5
  9V@3A           └──────────────────────┘
                                                │
                                          ┌─────┴─────┐
                                          │ PiSugar 3 │ ◄── UPS / portable
                                          │   Plus    │     mode only
                                          └───────────┘
```

**Rules:**
- **Primary power (mains):** Feed through NPU adapter's USB-C PD (≥27W, 9V@3A).
- **PiSugar 3 Plus:** UPS and portable mode only. NOT for sustained NPU inference.
- **Never power from Pi 5's USB-C when NPU PiHat is connected.**
- Add `PSU_MAX_CURRENT=5000` to `/boot/firmware/config.txt` if powering from non-PD source.

### Checklist Before Starting
- [ ] Raspberry Pi 5 (8GB)
- [ ] M5Stack LLM-8850 card + M.2 adapter (PiHat or RPi HAT+)
- [ ] PCIe FPC ribbon cable
- [ ] PiSugar 3 Plus + battery
- [ ] PiSugar Whisplay HAT
- [ ] microSD card (64GB+, Class A2)
- [ ] USB-C PD power supply (≥27W)
- [ ] Ethernet or WiFi credentials
- [ ] Optional: USB SSD for extended storage

---

## 0.2 OS Installation & Hardening

### Flash OS
Raspberry Pi Imager → **Raspberry Pi OS (64-bit, Debian 12 Bookworm)**

Pre-configure in Imager:
- Hostname: `cortex`
- SSH: Enable (key-based preferred)
- WiFi: Configure if needed
- Locale/timezone: Set correctly

### First Boot (Pi only, no HATs)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y \
    git curl wget htop tmux vim \
    python3-pip python3-venv python3-dev \
    build-essential cmake \
    i2c-tools spi-tools \
    alsa-utils \
    sqlite3 libsqlite3-dev \
    nftables \
    bubblewrap
sudo reboot
```

### SSH Hardening

```bash
# After confirming key auth works:
sudo nano /etc/ssh/sshd_config
# PermitRootLogin no
# PasswordAuthentication no
# MaxAuthTries 3
sudo systemctl restart sshd
```

### Firewall

```bash
sudo systemctl enable nftables
sudo nft flush ruleset
sudo nft -f - <<'EOF'
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif lo accept
        tcp dport 22 accept
        tcp dport 8080 accept
        tcp dport 8421 accept
        ip protocol icmp accept
        ip6 nexthdr icmpv6 accept
        log prefix "nftables-drop: " drop
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF
sudo nft list ruleset | sudo tee /etc/nftables.conf
```

### Service Account

```bash
sudo useradd -r -s /usr/sbin/nologin -m -d /opt/cortex cortex
sudo usermod -aG i2c,spi,gpio,audio cortex
```

### Enable Interfaces

```bash
sudo raspi-config
# Enable: I2C, SPI, PCIe/M.2
# Verify after reboot:
ls /dev/i2c-*
ls /dev/spidev*
```

---

## 0.3 Assembly & Verification

**⚠️ Power off completely before each hardware change.**

### Order: PiSugar (back) → NPU adapter (PCIe) → Whisplay HAT (GPIO top)

### Verify after power on:

```bash
# I2C devices
sudo i2cdetect -y 1
# Expected: 0x1a (WM8960), 0x57 (PiSugar EEPROM), 0x68 (RTC), 0x75 (PiSugar MCU)

# PCIe
lspci
# Expected: Axera AX8850 or similar
```

---

## 0.4 Drivers

### PiSugar Power Manager

```bash
wget https://cdn.pisugar.com/release/pisugar-power-manager.sh
bash pisugar-power-manager.sh -c release
# Verify: http://cortex.local:8421
# IMPORTANT: Disable AUTO switch to avoid I2C conflicts
```

### Whisplay HAT

```bash
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay/Driver
sudo bash install_wm8960_drive.sh
sudo reboot
# Verify: aplay -l (should show wm8960)
# Test: cd ~/Whisplay/example && sudo bash run_test.sh
```

### AXCL Runtime (NPU)

```bash
sudo wget -qO /etc/apt/keyrings/StackFlow.gpg \
    https://repo.llm.m5stack.com/m5stack-apt-repo/key/StackFlow.gpg
echo 'deb [signed-by=/etc/apt/keyrings/StackFlow.gpg] \
    https://repo.llm.m5stack.com/m5stack-apt-repo axclhost main' | \
    sudo tee /etc/apt/sources.list.d/axclhost.list
sudo apt update
sudo apt install axcl-smi axcl-run
source ~/.bashrc
axcl-smi  # Should show NPU with ~7040 MiB CMM
```

---

## 0.4.1 Peripheral Verification

After drivers are installed, verify each Whisplay peripheral individually before running full validation tests.

### Speaker Output
```bash
# Play a test tone through Whisplay speaker
speaker-test -D plughw:<CARD>,0 -t sine -f 440 -l 1
# Or play a WAV file:
aplay -D plughw:<CARD>,0 /usr/share/sounds/alsa/Front_Center.wav
# Verify: audible sound from speaker
```

### LCD Display
```bash
cd ~/Whisplay/example
# Run the Whisplay display test:
sudo python3 display_test.py  # or equivalent from run_test.sh
# Verify: visual output on 1.69" LCD (colored pattern, text, or image)
# If no dedicated test script, verify LCD works during run_test.sh
```

### Button Input
```bash
python3 -c "
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BOARD)
GPIO.setup(11, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
print('Press the button (Ctrl+C to exit)...')
try:
    while True:
        if GPIO.input(11):  # Active HIGH (pressed=1)
            print('Button PRESSED')
        time.sleep(0.05)
except KeyboardInterrupt:
    GPIO.cleanup()
"
# Verify: "Button PRESSED" appears on each press
# NOTE: Button is active-HIGH (pressed=1), uses RPi.GPIO BOARD pin numbering
```

### RGB LEDs
```bash
python3 -c "
import RPi.GPIO as GPIO
import time
GPIO.setmode(GPIO.BOARD)
# LEDs are active-LOW (0=on, 100=off via PWM)
for pin, color in [(22, 'RED'), (18, 'GREEN'), (16, 'BLUE')]:
    GPIO.setup(pin, GPIO.OUT)
    pwm = GPIO.PWM(pin, 1000)
    pwm.start(0)  # 0% duty = full brightness (active-low)
    print(f'{color} on')
    time.sleep(1)
    pwm.stop()
GPIO.cleanup()
print('LED test complete')
"
# Verify: LEDs cycle red → green → blue
# NOTE: LEDs are active-LOW via PWM on pins 22/18/16 (BOARD numbering)
```

---

## 0.5 Validation Tests

### Test 1a: Quick LLM (Qwen3-0.6B)
```bash
cd ~ && mkdir -p models && cd models
git clone https://huggingface.co/M5Stack/Qwen3-0.6B-ax650 --depth 1
# Run and record: tokens/sec, TTFT, NPU memory
```

### Test 1b: Primary LLM (Qwen3-1.7B)
```bash
cd ~/models
git clone https://huggingface.co/AXERA-TECH/Qwen3-1.7B-w8a16-ax650 --depth 1
# Run and record: tokens/sec, TTFT, NPU memory (CMM)
# Expected: ~7.38 tok/s, ~3.3 GB CMM
# Compare with 0.6B results from Test 1a
```

### Test 2: ASR (SenseVoice)
```bash
git clone https://huggingface.co/M5Stack/SenseVoiceSmall-axmodel --depth 1
# Run with test audio, record: RTF, accuracy, memory
```

### Test 3: Mic → ASR Pipeline
```bash
# IMPORTANT: Use ALSA 'default' device, NOT hw:0,0. WM8960 requires 2-channel
# capture. The /etc/asound.conf routes 'default' through plug→dsnoop chain.
arecord -D default -f S16_LE -r 16000 -c 1 -d 5 test_mic.wav
# Feed to SenseVoice, verify end-to-end
# Verified Session 16: "This is a test." transcribed in 0.17s
```

### Test 4: Multi-Model Memory Budget (CRITICAL)
```bash
# Monitor: watch -n 1 axcl-smi
# Load SenseVoice → record CMM
# Load Qwen3-1.7B → record CMM
# Load Kokoro-82M → record CMM (expect ~237 MiB)
# Load SmolVLM2-500M → record CMM (expect ~500 MiB)
# Can all 4 co-exist? Target total < 4.75GB
# Record: individual sizes, total, remaining CMM headroom
```

### Test 5: Battery Under Load
```bash
# Full charge → sustained inference → record drain rate
# Check for under-voltage: dmesg | grep -i voltage
```

### Test 6: I2C Health Under Load
```bash
# During NPU inference: sudo i2cdetect -y 1
# All addresses still visible?
```

### Test 7: TTS Quality Validation (Kokoro)
```bash
# Load Kokoro-82M on NPU
# Feed test sentences: "Hello, how are you today?", "The weather is sunny and warm."
# Play output through Whisplay speaker
# Record: RTF (expect ~0.067), audio quality (intelligibility), NPU memory
# Test at least 3 different voice IDs (e.g., af_heart, am_adam, bf_emma)
```

### Test 8: Vision Model (FastVLM-0.5B)
```bash
# Download from AXERA-TECH HuggingFace (replaces SmolVLM2-500M — see DD-045)
hf download AXERA-TECH/FastVLM-0.5B --local-dir ~/models/FastVLM-0.5B
# Requires pyaxengine (pip install axengine wheel from AXERA-TECH GitHub)
# Run via Python (no AXCL aarch64 C++ binary available):
cd ~/models/FastVLM-0.5B
python3 infer_axmodel_650.py \
  -v ./fastvlm_C128_CTX1024_P640_ax650/image_encoder_512x512_0.5b_ax650.axmodel \
  -m ./fastvlm_C128_CTX1024_P640_ax650 \
  -t fastvlm_tokenizer -i 512
# Interactive: enter image path, then 'q' to quit
# Record: inference time, description quality, NPU memory usage
```

### Test 9: CSI Camera (if hardware available)
```bash
# If CSI camera module is attached:
python3 -c "
from picamera2 import Picamera2
cam = Picamera2()
cam.start()
cam.capture_file('test_capture.jpg')
cam.stop()
print('Capture successful')
"
# Verify: image quality, capture latency
# If no camera: mark as SKIPPED in checklist
```

---

## 0.6 Phase 0 Investigations

These are research questions, not pass/fail tests. Document findings for each.

### Investigation 1: Speculative Decoding
**Question:** Does AXCL runtime support draft/verify pattern (Qwen3-0.6B drafts, Qwen3-1.7B verifies)?
```bash
# Load both Qwen3-0.6B and Qwen3-1.7B simultaneously
# Check AXCL API docs for draft_model / speculative_decoding parameters
# If supported: measure tok/s improvement and verify output quality
# Expected result: likely NOT supported (AXCL is inference-only, not training-aware)
```
**Result:** not supported
**Notes:** `main_axcl_aarch64` binary has no `--draft_model` parameter. Each model loads all layers from a single template. No AXCL API for draft/verify pattern. `--devices` flag is for data parallelism across NPU cards, not speculative decoding.

### Investigation 2: Constrained Generation
**Question:** Does AXCL support grammar-guided or logit-biased decoding for structured tool call output?
```bash
# Test axcl-run with logit_bias parameter (if available)
# Test if llama.cpp GBNF grammar support works via AXCL backend
# Alternative: test if output can be constrained via stop tokens
# Expected result: limited (stop tokens likely, full grammar unlikely)
```
**Result:** stop tokens only
**Notes:** `post_config.json` supports temperature, top_p, top_k, repetition_penalty (sampling params only). No grammar or logit_bias parameters in the binary. Default is top_k=1 (greedy). Tool calling will rely on system prompt (Hermes template) + post-generation output parsing. The `axllm` binary (newer, from ax-llm repo) offers OpenAI-compatible API that may support stop sequences.

### Investigation 3: Moonshine ASR
**Question:** Is Moonshine Tiny (26MB) a viable complement to SenseVoice for streaming partial transcription?
```bash
pip install moonshine-onnx
# Run Moonshine on CPU with test audio
# Compare: WER vs SenseVoice, latency profile, streaming capability
# Key question: can it provide partial results while button is held?
```
**Result:** not needed
**Notes:** No .axmodel exists for Moonshine on AX650N. SenseVoice already achieves RTF 0.028 on NPU with WER 0.02. SenseVoice also has `streaming_sensevoice.axmodel` for streaming partial transcription. Running Moonshine on CPU would be slower and less accurate than SenseVoice on NPU.

### Investigation 4: Unified Multimodal (Qwen3-VL-2B)
**Question:** Can Qwen3-VL-2B replace both Qwen3-1.7B (LLM) and SmolVLM2-500M (VLM) as a single model?
```bash
git clone https://huggingface.co/AXERA-TECH/Qwen3-VL-2B-ax650 --depth 1
# Test 1: Text-only tool calling accuracy (compare vs Qwen3-1.7B)
#   Run same prompts, compare function call output
# Test 2: Vision quality (compare vs SmolVLM2-500M)
#   Same test images, compare description quality
# Note: 7.80 tok/s, 3.7 GB — fits but uses more memory than 1.7B
```
**Result:** ADOPTED (DD-051, 2026-03-04)
**Notes:** Originally rejected for flexibility reasons. Revisited with GPTQ-Int4 quantization: Qwen3-VL-2B-Instruct-GPTQ-Int4 measured at 1,771 MiB CMM (vs 3,375+792=4,167 MiB for Qwen3-1.7B+FastVLM), ~10 tok/s (1.3x faster than Qwen3-1.7B), built-in vision, OpenAI-compatible API via `axllm serve`, no separate tokenizer server. Memory savings: 2,396 MiB. New 3-model total: 2,254 MiB (32% of NPU, 68% headroom). The flexibility tradeoff is acceptable — Qwen3-0.6B retained as fast fallback. axllm binary must be compiled from source (axllm branch of AXERA-TECH/ax-llm). See §0.8 for full setup instructions.

---

## 0.7 Completion Checklist

```
HARDWARE VALIDATION
[x] All components assembled, no bus conflicts (PiSugar not connected — see notes)
[x] NPU detected via lspci and axcl-smi (AX650N, firmware V3.6.4)
[x] Speaker produces audible output (speaker-test 440Hz + aplay WAV)
[x] LCD displays test pattern (240x280 ST7789, SPI0, color cycling verified)
[x] Button press detected on pin 11 (BOARD numbering, active-HIGH via RPi.GPIO)
[x] RGB LEDs cycle through red/green/blue (PWM via pins 22/18/16 BOARD)
[x] Microphone captures audio (arecord 16kHz mono via ALSA 'default' device — see DD-049)
[ ] PiSugar reports battery and charging state — NOT CONNECTED (pogo pins not in contact)
[ ] CSI camera captures image — SKIPPED (no camera attached)
[x] I2C stable under NPU load (0x1a=WM8960 UU, 0x40=Whisplay component)

NPU METRICS (measured 2026-03-02, updated 2026-03-04)
Total CMM:              7040 MiB
SenseVoice size:        251 MiB (CMM during operation)
Qwen3-VL-2B size:       1771 MiB (CMM measured, GPTQ-Int4, DD-051)
Kokoro-82M size:        232 MiB (CMM during operation)
All 3 co-resident:      YES (total: 2,254 MiB, headroom: 4,786 MiB / 68%)
Qwen3-0.6B tok/s:       13.74
Qwen3-VL-2B tok/s:      ~10 (measured), max_token_len 2047
SenseVoice RTF:          0.028 (C++ AXCL aarch64 binary)
Kokoro RTF:              0.115 (Python), 0.067 (C++ — no aarch64 AXCL binary yet)
Kokoro audio quality:    GOOD (24kHz mono, natural voice, intelligible)
NPU idle temp:           41°C
NPU load temp:           50°C (during VLM inference)

REPLACED MODELS (historical, pre DD-051)
Qwen3-1.7B size:        3375 MiB (CMM including 2047-token KV cache) — replaced by Qwen3-VL-2B
Qwen3-1.7B tok/s:       7.70
FastVLM-0.5B size:      792 MiB — replaced by Qwen3-VL-2B built-in vision

POWER METRICS
Battery capacity:    N/A — PiSugar not connected
Active drain:        N/A
Idle drain:          N/A
Under-voltage:       NO (mains powered via NPU adapter)
Stable under load:   YES

INVESTIGATIONS
Speculative decoding:     not supported (no draft_model in binary)
Constrained generation:   stop tokens only (post_config.json: temp/top_p/top_k/rep_penalty)
Moonshine ASR:            not needed (SenseVoice has streaming_sensevoice.axmodel on NPU)
Unified multimodal (VL-2B): ADOPTED (DD-051 — GPTQ-Int4 measured 1771 MiB, 68% headroom)

SYSTEM
OS:                  Debian 12 Bookworm (Raspberry Pi OS 64-bit)
Kernel:              6.12.62+rpt-rpi-2712
AXCL driver:         V3.6.4 (axclhost v3.6.5 package, 6 DKMS kernel modules)
Python:              3.11.2
Free disk:           ~44 GB (after model downloads)
```

---

## 0.8 Model Setup Notes (Tested 2026-03-02)

Detailed setup instructions for each model, including gotchas discovered during Phase 0.

### AXCL Runtime (required by all models)

```bash
# Single package installs driver + tools (NOT axcl-smi / axcl-run separately)
sudo apt install axclhost
# Builds 6 kernel modules via DKMS: axcl_host, ax_pcie_host_dev, ax_pcie_mmb,
#   ax_pcie_msg, ax_pcie_net_host, ax_pcie_p2p_rc
# After install, must run: source /etc/profile
# Tools installed to /usr/bin/axcl/ (axcl-smi, axcl_run_model, etc.)
# Verify: axcl-smi → should show AX650N with 7040 MiB CMM
```

### Python Environment

```bash
# Bookworm uses PEP 668 (externally-managed-environment)
# System packages via apt:
sudo apt install python3-pil python3-pygame python3-rpi-lgpio python3-spidev
# Model-specific packages in a venv:
python3 -m venv ~/.venvs/axllm
source ~/.venvs/axllm/bin/activate
pip install transformers jinja2 huggingface_hub  # for LLM tokenizer server
pip install axengine  # from AXERA-TECH GitHub releases (pyaxengine)
# HuggingFace CLI is now 'hf' (not 'huggingface-cli')
```

### Qwen3-0.6B / Qwen3-1.7B (LLM)

```bash
# Download models
hf download AXERA-TECH/Qwen3-0.6B --local-dir ~/models/Qwen3-0.6B
hf download AXERA-TECH/Qwen3-1.7B --local-dir ~/models/Qwen3-1.7B
chmod +x ~/models/Qwen3-*/main_axcl_aarch64

# GOTCHA: Requires separate tokenizer HTTP server on port 12345
cd ~/models/Qwen3-0.6B  # or Qwen3-1.7B — tokenizer is the same
~/.venvs/axllm/bin/python qwen3_tokenizer_uid.py --port 12345 &
# Then run the model:
bash run_qwen3_0.6b_int8_ctx_axcl_aarch64.sh

# Key parameters differ between 0.6B and 1.7B:
#   0.6B: tokens_embed_size=1024, axmodel_num=28
#   1.7B: tokens_embed_size=2048, axmodel_num=28
# Model load: ~23s (0.6B), ~43s (1.7B). Interactive prompt loop.
```

### Qwen3-VL-2B (Primary VLM — DD-051, replaces Qwen3-1.7B + FastVLM-0.5B)

```bash
# Step 1: Download pre-compiled model weights from AXERA-TECH
cd ~/Cortex
.venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('AXERA-TECH/Qwen3-VL-2B-Instruct-GPTQ-Int4',
                  local_dir='/home/andrew/models/Qwen3-VL-2B')
"
# Download size: ~4.1 GB (79 files). Takes ~10 minutes.

# Step 2: Compile axllm binary from source (REQUIRED — no pre-built binary available)
cd /tmp
git clone --branch axllm --depth 1 https://github.com/AXERA-TECH/ax-llm.git
cd ax-llm
git submodule update --init --recursive
mkdir build_native && cd build_native
cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_AX650=OFF -DBUILD_AXCL=ON ..
make -j4
# Build takes ~5 minutes on Pi 5. Produces: install/bin/axllm (2.2MB ELF aarch64)
cp install/bin/axllm ~/models/Qwen3-VL-2B/axllm
chmod +x ~/models/Qwen3-VL-2B/axllm

# Step 3: Create config.json in model directory (REQUIRED by axllm serve)
cat > ~/models/Qwen3-VL-2B/config.json << 'CONF'
{
    "template_filename_axmodel": "Qwen3-VL-2B-Instruct-AX650-c128_p1152-int4/qwen3_vl_text_p128_l%d_together.axmodel",
    "filename_post_axmodel": "Qwen3-VL-2B-Instruct-AX650-c128_p1152-int4/qwen3_vl_text_post.axmodel",
    "url_tokenizer_model": "qwen3_tokenizer.txt",
    "tokenizer_type": "Qwen3VL",
    "filename_tokens_embed": "Qwen3-VL-2B-Instruct-AX650-c128_p1152-int4/model.embed_tokens.weight.bfloat16.bin",
    "post_config_path": "post_config.json",
    "axmodel_num": 28,
    "tokens_embed_num": 151936,
    "tokens_embed_size": 2048,
    "b_use_mmap_load_embed": true,
    "devices": [0],
    "model_name": "qwen3-vl-2b",
    "system_prompt": "You are Cortex, a helpful voice assistant."
}
CONF

# Step 4: Verify standalone
cd ~/models/Qwen3-VL-2B
./axllm serve . --port 8080 &
# Wait ~45 seconds for model to load (28 layers + post model)
curl -s http://127.0.0.1:8080/v1/models  # Should return model list
curl -s -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-vl-2b","messages":[{"role":"user","content":"What is 2+2?"}]}'
# Expected: {"choices":[{"message":{"content":"4",...}}]}
kill %1

# GOTCHA: No pre-built binary. Must compile from axllm branch of ax-llm repo.
# GOTCHA: tokenizer_type MUST be "Qwen3VL" (not "tiktoken" or "qwen3").
#   See ax-llm/third_party/tokenizer.axera/src/Qwen3Tokenizer.hpp:
#   REGISTER(Qwen3VL, qwen3vl_tokenizer)
# GOTCHA: Default port is 8080 (not 8000). VLMRunner uses 8080.
# GOTCHA: config.json is required in model directory — axllm reads it on startup.
#   The old main_axcl_aarch64 used shell scripts with CLI args; axllm uses JSON.
# GOTCHA: No separate tokenizer server needed (integrated into axllm binary).
# GOTCHA: Model load takes ~45 seconds (28 layer axmodels + post model + embeddings).
# Measured: 1,771 MiB CMM, ~10 tok/s, max_token_len 2047, 50°C under load.
```

### SenseVoice ASR

```bash
hf download AXERA-TECH/SenseVoice --local-dir ~/models/SenseVoice
chmod +x ~/models/SenseVoice/cpp/axcl_aarch64/main

# C++ AXCL binary (fastest, no Python deps needed):
cd ~/models/SenseVoice
LD_LIBRARY_PATH=cpp/axcl_aarch64 ./cpp/axcl_aarch64/main \
  -a example/en.mp3 -t sensevoice -p sensevoice_ax650 -l en
# Supports: wav, mp3. Languages: en, zh, ja, ko, yue, auto

# GOTCHA: Python path requires PyTorch (heavy). Use C++ binary instead.
# GOTCHA: Streaming model exists (streaming_sensevoice.axmodel) but
#   only the offline binary is pre-compiled for AXCL aarch64.
```

### Kokoro-82M TTS

```bash
hf download AXERA-TECH/Kokoro --local-dir ~/models/Kokoro

# Python path (AXCL via pyaxengine):
pip install kokoro soundfile 'misaki[en]' onnxruntime ordered_set scipy \
  pypinyin cn2an jieba pyopenjtalk 'fugashi[unidic-lite]' jaconv mojimoji Pillow
python -m spacy download en_core_web_sm

# GOTCHA: Voice files must be .npy format (not .pt) for the AXERA inference code.
# Convert: python3 -c "import torch, numpy as np; \
#   v = torch.load('checkpoints/voices/af_heart.pt', weights_only=True); \
#   np.save('checkpoints/voices/af_heart.npy', v.numpy())"

cd ~/models/Kokoro
python3 kokoro_ax.py --text 'Hello world' --lang en \
  --voice checkpoints/voices/af_heart.npy --output out.wav -d models

# GOTCHA: No C++ AXCL aarch64 binary. C++ binaries are for AX650 native only.
#   Python RTF: 0.115. C++ (native AX650): 0.067. Phase 1 may need native build.
# GOTCHA: Init takes ~9s (loading 3 NPU models + 1 CPU ONNX vocoder).
```

### FastVLM-0.5B (VLM) — REPLACED by Qwen3-VL-2B (DD-051)

> **Note:** FastVLM-0.5B is no longer used. Qwen3-VL-2B provides built-in vision
> with better quality and lower total memory (1,771 vs 3,375+792 MiB). See §0.8
> "Qwen3-VL-2B" section above. Kept here for historical reference only.

```bash
hf download AXERA-TECH/FastVLM-0.5B --local-dir ~/models/FastVLM-0.5B
pip install Pillow  # needed in venv

# GOTCHA: No main_axcl_aarch64 binary. Only main_ax650 (native) and main_axcl_x86.
# Must use Python inference via pyaxengine:
cd ~/models/FastVLM-0.5B
python3 infer_axmodel_650.py \
  -v ./fastvlm_C128_CTX1024_P640_ax650/image_encoder_512x512_0.5b_ax650.axmodel \
  -m ./fastvlm_C128_CTX1024_P640_ax650 \
  -t fastvlm_tokenizer -i 512
# Interactive: enter image file path, get description. 'q' to quit.

# GOTCHA: Replaces SmolVLM2-500M from original scope doc (DD-045).
#   FastVLM-0.5B: 792 MiB CMM, 6x faster image encoding, better memory efficiency.
# GOTCHA: fastvlm_tokenizer requires trust_remote_code=True in transformers.
```

### Whisplay HAT (LCD/Button/LEDs/Audio)

```bash
# Driver at ~/Whisplay/Driver/WhisPlay.py
# GOTCHA: Uses RPi.GPIO with BOARD pin numbering (not BCM, not gpiod)
#   Physical pin 11 = button (active-HIGH: pressed=1, released=0)
#   Physical pin 22/18/16 = RGB LEDs (PWM, active-low: 0=on, 255=off)
#   Physical pin 15 = LCD backlight, pin 13 = DC, pin 7 = RST
# GOTCHA: python3-rpi-lgpio (lgpio compatibility shim) has cosmetic PWM
#   cleanup bug — TypeError in __del__. Non-blocking, ignore it.
# LCD: 240x280 ST7789 via SPI0 at 100MHz. RGB565 pixel format.
# Audio: WM8960 codec at card 0. Speaker + mic on same I2S bus.
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `lspci` empty | Reseat FPC cable, enable PCIe in raspi-config |
| I2C all `UU` | Disable PiSugar AUTO switch |
| No sound | Specify WM8960 card number explicitly |
| Noisy/garbled mic audio | Use ALSA `default` device, NOT `hw:0,0`. WM8960 requires 2-channel capture — the `default` device routes through plug→dsnoop chain (DD-049) |
| Mic audio clipping | Reduce Capture Volume (try 50-55/63). Run `scripts/setup-mixer.sh` for tested defaults |
| `arecord -c 1` fails on hw:0,0 | Expected — WM8960 hw requires stereo. Use `-D default` instead |
| Button GPIO "no event loop in thread" | RPi.GPIO callbacks run on background thread. Use `asyncio.run_coroutine_threadsafe()` |
| Under-voltage | Use mains power; battery for light tasks |
| NPU > 75°C | Check fan, add ventilation |
| `axcl-smi` not found | `source ~/.bashrc` or re-login |
