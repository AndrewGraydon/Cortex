#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Cortex Dev Setup ==="

# Create venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Installing package in editable mode with dev deps..."
.venv/bin/pip install -e ".[dev]"

echo "Installing pre-commit hooks..."
.venv/bin/pre-commit install

echo "Running lint check..."
.venv/bin/ruff check src/ tests/ || true

echo "Running tests..."
.venv/bin/pytest -m "not hardware" --tb=short -q || true

echo ""
echo "=== Setup complete ==="
echo "Activate with: source .venv/bin/activate"
