"""Phase 6 end-to-end validation — all 4 exit criteria.

EC#1: Soak test framework works (validates structure, not 24h duration)
EC#2: Backup + restore cycle with data integrity verified
EC#3: Fault injection per DD-033 matrix degrades gracefully
EC#4: Security audit items resolved
"""

from __future__ import annotations

import tarfile
import time
from pathlib import Path

import aiosqlite
import pytest

from cortex.maintenance.integrity import check_sqlite_integrity, verify_backup
from cortex.maintenance.retention import run_all_retention
from cortex.resilience.circuit_breaker import CircuitBreaker, CircuitState
from cortex.resilience.degradation import DegradationEngine
from cortex.security.audit import SqliteAuditLog
from cortex.security.audit_integrity import compute_entry_hmac, verify_chain
from cortex.security.log_redactor import redact_string
from cortex.security.rate_limiter import RateLimiter
from cortex.security.types import AuditEntry


class TestEC1SoakFramework:
    """EC#1: Soak test framework validates sustained operation."""

    def test_degradation_engine_continuous_evaluation(self):
        """Engine correctly evaluates 100 consecutive states."""
        engine = DegradationEngine()
        breakers = {
            "llm": CircuitBreaker("llm"),
            "tts": CircuitBreaker("tts"),
            "asr": CircuitBreaker("asr"),
        }

        for i in range(100):
            if i % 20 == 10:
                breakers["llm"].force_open()
            elif i % 20 == 0:
                breakers["llm"].reset()

            state = engine.evaluate(breakers=breakers)
            if breakers["llm"].is_open:
                assert not state.llm_available
            else:
                assert state.llm_available

    async def test_circuit_breaker_lifecycle(self):
        """Full lifecycle: CLOSED → OPEN → HALF_OPEN → CLOSED."""
        import asyncio

        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout_s=0.1)
        assert cb.state == CircuitState.CLOSED

        cb.record_failure("err1")
        cb.record_failure("err2")
        assert cb.state == CircuitState.OPEN

        await asyncio.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_resource_tracking_available(self):
        """Resource tracking tools are available on this platform."""
        import resource as res

        usage = res.getrusage(res.RUSAGE_SELF)
        assert usage.ru_maxrss > 0


class TestEC2BackupRestoreIntegrity:
    """EC#2: Backup + restore cycle with data integrity verified."""

    async def test_sqlite_integrity_check(self, tmp_path: Path) -> None:
        """SQLite integrity check passes on valid database."""
        db_path = str(tmp_path / "test.db")
        async with aiosqlite.connect(db_path) as db:
            await db.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, value TEXT)")
            await db.execute("INSERT INTO data VALUES (1, 'test')")
            await db.commit()

        result = await check_sqlite_integrity(db_path)
        assert result.ok is True

    async def test_corrupt_db_detected(self, tmp_path: Path) -> None:
        """Integrity check detects corrupt database."""
        corrupt = tmp_path / "corrupt.db"
        corrupt.write_bytes(b"not a database" * 100)
        result = await check_sqlite_integrity(str(corrupt))
        assert result.ok is False

    def test_backup_tarball_verification(self, tmp_path: Path) -> None:
        """Backup tarball can be created and verified."""
        # Create test files
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "test.db").write_text("test data")
        (data_dir / "config.yaml").write_text("test: true")

        # Create tarball
        backup_path = str(tmp_path / "backup.tar.gz")
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(str(data_dir / "test.db"), arcname="data/test.db")
            tar.add(str(data_dir / "config.yaml"), arcname="data/config.yaml")

        # Verify
        result = verify_backup(backup_path)
        assert result.ok is True
        assert "2 files" in result.message

    def test_backup_restore_roundtrip(self, tmp_path: Path) -> None:
        """Create backup, extract, verify contents match."""
        # Create source
        source = tmp_path / "source"
        source.mkdir()
        (source / "data.txt").write_text("important data")

        # Create backup
        backup_path = str(tmp_path / "roundtrip.tar.gz")
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(str(source / "data.txt"), arcname="data.txt")

        # Extract to staging
        staging = tmp_path / "staging"
        staging.mkdir()
        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(str(staging), filter="data")

        # Verify
        restored = staging / "data.txt"
        assert restored.exists()
        assert restored.read_text() == "important data"

    async def test_retention_enforcement(self, tmp_path: Path) -> None:
        """Data retention correctly deletes old entries."""
        audit_path = str(tmp_path / "audit.db")
        memory_path = str(tmp_path / "memory.db")
        now = time.time()

        # Create audit DB with old and recent entries
        async with aiosqlite.connect(audit_path) as db:
            await db.execute("""CREATE TABLE audit_log (
                id TEXT PRIMARY KEY, timestamp REAL NOT NULL,
                action_type TEXT DEFAULT 'test', hmac TEXT DEFAULT ''
            )""")
            await db.execute(
                "INSERT INTO audit_log (id, timestamp) VALUES ('old', ?)",
                (now - 100 * 86400,),
            )
            await db.execute(
                "INSERT INTO audit_log (id, timestamp) VALUES ('new', ?)",
                (now - 5 * 86400,),
            )
            await db.commit()

        # Create memory DB
        async with aiosqlite.connect(memory_path) as db:
            await db.execute("""CREATE TABLE conversations (
                id TEXT PRIMARY KEY, created_at REAL NOT NULL, summary TEXT DEFAULT ''
            )""")
            await db.execute(
                "INSERT INTO conversations (id, created_at) VALUES ('old', ?)",
                (now - 60 * 86400,),
            )
            await db.execute(
                "INSERT INTO conversations (id, created_at) VALUES ('new', ?)",
                (now - 5 * 86400,),
            )
            await db.commit()

        result = await run_all_retention(
            audit_db_path=audit_path,
            memory_db_path=memory_path,
            audit_retention_days=90,
            memory_retention_days=30,
        )
        assert result.audit_deleted == 1
        assert result.conversations_deleted == 1
        assert result.total_deleted == 2


class TestEC3FaultInjectionDD033:
    """EC#3: All 8 DD-033 scenarios degrade gracefully."""

    @pytest.fixture()
    def dd033_system(self) -> tuple[DegradationEngine, dict[str, CircuitBreaker]]:
        engine = DegradationEngine()
        breakers = {
            "llm": CircuitBreaker("llm"),
            "tts": CircuitBreaker("tts"),
            "asr": CircuitBreaker("asr"),
        }
        return engine, breakers

    def test_scenario_1_llm_fail(self, dd033_system):
        engine, breakers = dd033_system
        breakers["llm"].force_open()
        state = engine.evaluate(breakers=breakers)
        assert not state.llm_available
        assert any("timers" in m for m in state.user_messages)

    def test_scenario_2_tts_fail(self, dd033_system):
        engine, breakers = dd033_system
        breakers["tts"].force_open()
        state = engine.evaluate(breakers=breakers)
        assert not state.tts_available
        assert any("screen" in m for m in state.user_messages)

    def test_scenario_3_asr_fail(self, dd033_system):
        engine, breakers = dd033_system
        breakers["asr"].force_open()
        state = engine.evaluate(breakers=breakers)
        assert not state.asr_available
        assert any("web UI" in m for m in state.user_messages)

    def test_scenario_4_network_down(self, dd033_system):
        engine, breakers = dd033_system
        state = engine.evaluate(breakers=breakers, network_ok=False)
        assert not state.network_available
        assert any("local-only" in m for m in state.user_messages)

    def test_scenario_5_battery_low(self, dd033_system):
        engine, breakers = dd033_system
        state = engine.evaluate(breakers=breakers, battery_pct=10.0)
        assert not state.power_ok
        assert any("low" in m.lower() for m in state.user_messages)

    def test_scenario_6_battery_critical(self, dd033_system):
        engine, breakers = dd033_system
        state = engine.evaluate(breakers=breakers, battery_pct=3.0)
        assert not state.power_ok
        assert any("shutting down" in m.lower() for m in state.user_messages)

    def test_scenario_7_storage_full(self, dd033_system):
        engine, breakers = dd033_system
        state = engine.evaluate(
            breakers=breakers,
            health={"storage": {"used_pct": 98.0}},
        )
        assert not state.storage_ok
        assert any("storage" in m.lower() for m in state.user_messages)

    def test_scenario_8_service_crash_recovery(self, dd033_system):
        engine, breakers = dd033_system
        breakers["llm"].force_open()
        state = engine.evaluate(breakers=breakers)
        assert not state.llm_available
        breakers["llm"].reset()
        state = engine.evaluate(breakers=breakers)
        assert state.llm_available
        assert state.is_fully_operational


class TestEC4SecurityAudit:
    """EC#4: Security audit items resolved."""

    def test_rate_limiter_blocks_after_threshold(self):
        limiter = RateLimiter(max_attempts=3, window_seconds=10.0)
        for _ in range(3):
            limiter.record("attacker-ip")
        result = limiter.check("attacker-ip")
        assert not result.allowed
        assert result.retry_after > 0

    async def test_audit_hmac_chain(self, tmp_path: Path) -> None:
        """Audit log maintains HMAC chain integrity."""
        audit = SqliteAuditLog(db_path=str(tmp_path / "audit.db"))
        await audit.start()

        for i in range(5):
            entry = AuditEntry(
                id=f"entry-{i}",
                timestamp=time.time() + i,
                action_type="test_action",
                action_id=f"action-{i}",
            )
            await audit.log(entry)

        valid, bad_idx = await audit.verify_integrity()
        assert valid is True
        assert bad_idx == -1
        await audit.stop()

    def test_hmac_tamper_detection(self):
        """HMAC chain detects tampered entries."""
        entries = []
        prev_hmac = ""
        for i in range(3):
            data = {"id": f"e{i}", "timestamp": float(i)}
            hmac_val = compute_entry_hmac(data, prev_hmac)
            entries.append({**data, "hmac": hmac_val})
            prev_hmac = hmac_val

        # Tamper with middle entry
        entries[1]["timestamp"] = 999.0
        valid, bad_idx = verify_chain(entries)
        assert valid is False
        assert bad_idx == 1

    def test_log_redaction(self):
        """Sensitive data is redacted from logs."""
        assert "[REDACTED]" in redact_string("password=secret123")
        assert "[REDACTED]" in redact_string("Bearer sk-abc123xyz")
        assert "[REDACTED]" in redact_string("api_key=12345678901234567890123456789012")

    def test_rate_limiter_per_ip_isolation(self):
        """Rate limits are tracked independently per IP."""
        limiter = RateLimiter(max_attempts=2, window_seconds=10.0)
        limiter.record("ip1")
        limiter.record("ip1")
        assert not limiter.check("ip1").allowed
        assert limiter.check("ip2").allowed

    def test_rate_limiter_reset(self):
        """Successful auth resets rate limit."""
        limiter = RateLimiter(max_attempts=2, window_seconds=10.0)
        limiter.record("ip")
        limiter.record("ip")
        assert not limiter.check("ip").allowed
        limiter.reset("ip")
        assert limiter.check("ip").allowed
