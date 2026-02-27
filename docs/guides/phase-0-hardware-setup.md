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

## 0.5 Validation Tests

### Test 1: Quick LLM (Qwen3-0.6B)
```bash
cd ~ && mkdir -p models && cd models
git clone https://huggingface.co/M5Stack/Qwen3-0.6B-ax650 --depth 1
# Run and record: tokens/sec, TTFT, NPU memory
```

### Test 2: ASR (SenseVoice)
```bash
git clone https://huggingface.co/M5Stack/SenseVoiceSmall-axmodel --depth 1
# Run with test audio, record: RTF, accuracy, memory
```

### Test 3: Mic → ASR Pipeline
```bash
arecord -D plughw:<CARD>,0 -f S16_LE -r 16000 -c 1 -d 5 test_mic.wav
# Feed to SenseVoice, verify end-to-end
```

### Test 4: Multi-Model Memory Budget (CRITICAL)
```bash
# Monitor: watch -n 1 axcl-smi
# Load SenseVoice → record CMM
# Load Qwen3-1.7B → record CMM
# Load Kokoro-82M → record CMM (expect ~237 MiB)
# Can all 3 co-exist? Target total < 4.5GB (expect ~4.25GB)
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

---

## 0.6 Completion Checklist

```
HARDWARE VALIDATION
[ ] All components assembled, no bus conflicts
[ ] NPU detected via lspci and axcl-smi
[ ] Whisplay LCD, mic, speaker, buttons, LEDs all working
[ ] PiSugar reports battery and charging state

NPU METRICS (fill in actual values)
Total CMM:           _______ MiB
SenseVoice size:     _______ MiB
Qwen3-1.7B size:     _______ MiB
Kokoro-82M size:     _______ MiB (expected ~237 MiB)
All 3 co-resident:   YES / NO (total: _______ MiB, expected ~4250 MiB)
Qwen3-0.6B tok/s:    _______
Qwen3-1.7B tok/s:    _______
SenseVoice RTF:      _______
NPU idle temp:       _______°C
NPU load temp:       _______°C

POWER METRICS
Battery capacity:    _______ mAh
Active drain:        _______% / min → _______ min runtime
Idle drain:          _______% / min → _______ min runtime
Under-voltage:       YES / NO
Stable under load:   YES / NO

SYSTEM
OS:                  _______
Kernel:              _______
AXCL driver:         _______
Python:              _______
Free disk:           _______ GB
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `lspci` empty | Reseat FPC cable, enable PCIe in raspi-config |
| I2C all `UU` | Disable PiSugar AUTO switch |
| No sound | Specify WM8960 card number explicitly |
| Under-voltage | Use mains power; battery for light tasks |
| NPU > 75°C | Check fan, add ventilation |
| `axcl-smi` not found | `source ~/.bashrc` or re-login |
