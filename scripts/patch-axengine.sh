#!/usr/bin/env bash
# Patch axengine 0.1.3 vendor bugs.
#
# Two bugs in axengine's _axclrt.py (installed from AXERA-TECH local wheel):
#
# 1. CFFI pointer access: vnpu.value should be vnpu[0]
#    axclrtEngineVNpuKind* is a CFFI pointer, not a ctypes pointer.
#    CFFI pointers use [0] for dereferencing, not .value.
#
# 2. __del__ crash during Python shutdown: self._model_id can be None
#    during interpreter shutdown, causing TypeError in __del__.
#    Add null guard + try/except.
#
# Run on Pi after installing axengine:
#   bash scripts/patch-axengine.sh
#
# The patches are idempotent — safe to run multiple times.

set -euo pipefail

# Find the installed axengine _axclrt.py
# axengine prints [INFO] to stdout on import, so capture only the last line
AXCLRT=$(python3 -c "import axengine._axclrt as m; print(m.__file__)" 2>/dev/null | tail -1 || true)

if [ -z "$AXCLRT" ]; then
    echo "ERROR: axengine not installed or _axclrt.py not found"
    exit 1
fi

echo "Patching: $AXCLRT"

# --- Patch 1: Fix CFFI pointer access (vnpu.value → vnpu[0]) ---
if grep -q 'vnpu\.value' "$AXCLRT"; then
    sed -i 's/vnpu\.value/vnpu[0]/g' "$AXCLRT"
    echo "  [FIXED] vnpu.value → vnpu[0] (CFFI pointer access)"
else
    echo "  [OK] vnpu[0] already patched"
fi

# --- Patch 2: Guard __del__ against None during shutdown ---
if grep -q 'def __del__' "$AXCLRT" && ! grep -q 'if self._model_id is None' "$AXCLRT"; then
    # Replace the __del__ method with a guarded version
    python3 -c "
import re

with open('$AXCLRT', 'r') as f:
    content = f.read()

# Find and replace the __del__ method
old_del = re.search(r'(    def __del__\(self\):.*?)(?=\n    def |\nclass |\Z)', content, re.DOTALL)
if old_del:
    old = old_del.group(1)
    # Extract the body (everything after 'def __del__(self):')
    body_start = old.index(':') + 1
    body = old[body_start:]
    # Wrap in try/except with null guard
    new = '''    def __del__(self):
        if self._model_id is None:
            return
        try:''' + re.sub(r'^', '    ', body, flags=re.MULTILINE) + '''
        except Exception:
            pass  # Suppress errors during interpreter shutdown'''
    content = content.replace(old, new)
    with open('$AXCLRT', 'w') as f:
        f.write(content)
    print('  [FIXED] __del__ guarded against None during shutdown')
else:
    print('  [SKIP] __del__ method not found')
"
else
    echo "  [OK] __del__ already patched or not present"
fi

echo "Done. axengine patches applied."
