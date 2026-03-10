#!/usr/bin/env bash
# Run soak tests — sustained operation with fault injection
#
# Usage:
#   scripts/run-soak.sh              # dry-run (5 min, default)
#   scripts/run-soak.sh --full       # full 24h soak test
#   scripts/run-soak.sh --fault-only # fault injection tests only
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULTS_DIR="${CORTEX_RESULTS_DIR:-data}"
mkdir -p "${RESULTS_DIR}"

case "${1:-}" in
    --full)
        echo "Running full 24h soak test..."
        SOAK_DRY_RUN=0 pytest tests/soak/test_soak_24h.py -m soak -v \
            --tb=short 2>&1 | tee "${RESULTS_DIR}/soak-results-${TIMESTAMP}.log"
        ;;
    --fault-only)
        echo "Running fault injection tests..."
        pytest tests/soak/test_fault_injection.py -v --tb=short 2>&1 | \
            tee "${RESULTS_DIR}/fault-results-${TIMESTAMP}.log"
        ;;
    *)
        echo "Running dry-run soak test (5 min)..."
        SOAK_DRY_RUN=1 pytest tests/soak/test_soak_24h.py -m soak -v \
            --tb=short 2>&1 | tee "${RESULTS_DIR}/soak-results-${TIMESTAMP}.log"
        echo ""
        echo "Running fault injection tests..."
        pytest tests/soak/test_fault_injection.py -v --tb=short 2>&1 | \
            tee -a "${RESULTS_DIR}/soak-results-${TIMESTAMP}.log"
        ;;
esac

echo ""
echo "Results saved: ${RESULTS_DIR}/soak-results-${TIMESTAMP}.log"
