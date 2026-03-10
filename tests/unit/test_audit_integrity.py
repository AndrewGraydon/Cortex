"""Tests for audit HMAC chain — determinism, verification, tamper detection."""

from __future__ import annotations

from cortex.security.audit_integrity import compute_entry_hmac, verify_chain


class TestComputeEntryHmac:
    """HMAC computation."""

    def test_deterministic(self) -> None:
        entry = {"id": "1", "action_type": "test", "timestamp": 1000.0}
        h1 = compute_entry_hmac(entry, "")
        h2 = compute_entry_hmac(entry, "")
        assert h1 == h2

    def test_different_entries_different_hmac(self) -> None:
        e1 = {"id": "1", "action_type": "test"}
        e2 = {"id": "2", "action_type": "test"}
        assert compute_entry_hmac(e1, "") != compute_entry_hmac(e2, "")

    def test_chaining_changes_hmac(self) -> None:
        entry = {"id": "1", "action_type": "test"}
        h1 = compute_entry_hmac(entry, "")
        h2 = compute_entry_hmac(entry, "abc123")
        assert h1 != h2

    def test_returns_hex_string(self) -> None:
        entry = {"id": "1"}
        result = compute_entry_hmac(entry, "")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest


class TestVerifyChain:
    """Chain verification."""

    def test_empty_chain_is_valid(self) -> None:
        valid, idx = verify_chain([])
        assert valid is True
        assert idx == -1

    def test_single_entry_valid(self) -> None:
        entry_data = {"id": "1", "action_type": "test", "timestamp": 1.0}
        entry_hmac = compute_entry_hmac(entry_data, "")
        entry = {**entry_data, "hmac": entry_hmac}
        valid, idx = verify_chain([entry])
        assert valid is True
        assert idx == -1

    def test_two_entries_valid(self) -> None:
        e1_data = {"id": "1", "action_type": "test"}
        e1_hmac = compute_entry_hmac(e1_data, "")
        e1 = {**e1_data, "hmac": e1_hmac}

        e2_data = {"id": "2", "action_type": "query"}
        e2_hmac = compute_entry_hmac(e2_data, e1_hmac)
        e2 = {**e2_data, "hmac": e2_hmac}

        valid, idx = verify_chain([e1, e2])
        assert valid is True

    def test_tampered_entry_detected(self) -> None:
        e1_data = {"id": "1", "action_type": "test"}
        e1_hmac = compute_entry_hmac(e1_data, "")
        e1 = {**e1_data, "hmac": e1_hmac}

        e2_data = {"id": "2", "action_type": "query"}
        e2_hmac = compute_entry_hmac(e2_data, e1_hmac)
        e2 = {**e2_data, "hmac": e2_hmac}

        # Tamper with first entry
        e1["action_type"] = "HACKED"
        valid, idx = verify_chain([e1, e2])
        assert valid is False
        assert idx == 0

    def test_deleted_entry_detected(self) -> None:
        """Deleting an entry breaks the chain at the next entry."""
        entries_data = []
        previous_hmac = ""
        for i in range(3):
            data = {"id": str(i), "action_type": "test"}
            h = compute_entry_hmac(data, previous_hmac)
            entries_data.append({**data, "hmac": h})
            previous_hmac = h

        # Remove middle entry
        chain = [entries_data[0], entries_data[2]]
        valid, idx = verify_chain(chain)
        assert valid is False
        assert idx == 1  # Break at the entry after deletion

    def test_missing_hmac_detected(self) -> None:
        entry = {"id": "1", "action_type": "test"}
        valid, idx = verify_chain([entry])
        assert valid is False
        assert idx == 0

    def test_inserted_entry_detected(self) -> None:
        """Inserting an entry breaks the chain."""
        e1_data = {"id": "1", "action_type": "test"}
        e1_hmac = compute_entry_hmac(e1_data, "")
        e1 = {**e1_data, "hmac": e1_hmac}

        e2_data = {"id": "2", "action_type": "query"}
        e2_hmac = compute_entry_hmac(e2_data, e1_hmac)
        e2 = {**e2_data, "hmac": e2_hmac}

        # Insert a fake entry between them
        fake_data = {"id": "fake", "action_type": "evil"}
        fake_hmac = compute_entry_hmac(fake_data, e1_hmac)
        fake = {**fake_data, "hmac": fake_hmac}

        valid, idx = verify_chain([e1, fake, e2])
        assert valid is False
        assert idx == 2  # e2's chain is broken

    def test_long_chain_valid(self) -> None:
        entries = []
        previous_hmac = ""
        for i in range(100):
            data = {"id": str(i), "action_type": "test", "timestamp": float(i)}
            h = compute_entry_hmac(data, previous_hmac)
            entries.append({**data, "hmac": h})
            previous_hmac = h

        valid, idx = verify_chain(entries)
        assert valid is True
        assert idx == -1
