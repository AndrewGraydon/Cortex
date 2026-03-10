"""HMAC chain for audit log integrity — tamper detection.

Each audit entry is signed with HMAC(previous_hmac + entry_data).
Verifying the chain detects any insertion, deletion, or modification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Key for HMAC computation — from env or a dev default
_HMAC_KEY_ENV = "CORTEX_AUDIT_HMAC_KEY"
_DEV_KEY = "cortex-audit-dev-key"


def _get_hmac_key() -> bytes:
    """Get the HMAC key from environment or dev default."""
    key = os.environ.get(_HMAC_KEY_ENV, _DEV_KEY)
    return key.encode("utf-8")


def compute_entry_hmac(
    entry_data: dict[str, Any],
    previous_hmac: str = "",
) -> str:
    """Compute HMAC for an audit entry, chained to the previous entry.

    Args:
        entry_data: Dict of audit entry fields (id, timestamp, action_type, etc.)
        previous_hmac: HMAC of the previous entry ("" for the first entry).

    Returns:
        Hex-encoded HMAC string.
    """
    key = _get_hmac_key()
    # Canonical JSON representation for deterministic hashing
    canonical = json.dumps(entry_data, sort_keys=True, separators=(",", ":"))
    message = f"{previous_hmac}:{canonical}"
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_chain(entries: list[dict[str, Any]]) -> tuple[bool, int]:
    """Verify the HMAC chain of audit entries.

    Args:
        entries: List of audit entry dicts, each with an "hmac" field.
                 Must be in chronological order (oldest first).

    Returns:
        (valid, bad_index) — True if chain is valid; if invalid,
        bad_index is the first entry where verification fails.
    """
    previous_hmac = ""

    for i, entry in enumerate(entries):
        stored_hmac = entry.get("hmac", "")
        if not stored_hmac:
            logger.warning("Entry %d has no HMAC", i)
            return False, i

        # Recompute from entry data (excluding the hmac field itself)
        entry_data = {k: v for k, v in entry.items() if k != "hmac"}
        expected = compute_entry_hmac(entry_data, previous_hmac)

        if not hmac.compare_digest(stored_hmac, expected):
            logger.warning("HMAC chain broken at entry %d (id=%s)", i, entry.get("id", "?"))
            return False, i

        previous_hmac = stored_hmac

    return True, -1
