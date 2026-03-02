#!/usr/bin/env bash
# Install Cortex systemd services on Raspberry Pi.
# Run as: sudo ./scripts/install-services.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing Cortex systemd services from ${PROJECT_DIR}..."

# Copy unit files
for unit in cortex-npu cortex-audio cortex-display cortex-core; do
    src="${PROJECT_DIR}/config/systemd/${unit}.service"
    dst="${SYSTEMD_DIR}/${unit}.service"
    if [ -f "$src" ]; then
        cp "$src" "$dst"
        echo "  Installed: ${unit}.service"
    else
        echo "  WARNING: ${src} not found, skipping"
    fi
done

# Copy target
cp "${PROJECT_DIR}/config/systemd/cortex.target" "${SYSTEMD_DIR}/cortex.target"
echo "  Installed: cortex.target"

# Reload systemd
systemctl daemon-reload
echo "  systemd reloaded"

# Enable services
systemctl enable cortex.target
for unit in cortex-npu cortex-audio cortex-display cortex-core; do
    systemctl enable "${unit}.service"
    echo "  Enabled: ${unit}.service"
done

echo ""
echo "Cortex services installed. Start with:"
echo "  sudo systemctl start cortex.target"
echo ""
echo "Or start individually:"
echo "  sudo systemctl start cortex-npu"
echo "  sudo systemctl start cortex-audio"
echo "  sudo systemctl start cortex-display"
echo "  sudo systemctl start cortex-core"
