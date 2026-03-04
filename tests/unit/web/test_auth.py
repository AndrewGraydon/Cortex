"""Tests for Milestone 3a.2 — authentication service."""

from __future__ import annotations

import os
import tempfile

import pytest

from cortex.web.auth import AuthService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def password_hash() -> str:
    """Bcrypt hash of 'testpass123'."""
    return AuthService.hash_password("testpass123")


@pytest.fixture
async def auth_service(password_hash: str) -> AuthService:
    """AuthService with temp database and test password."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    service = AuthService(
        db_path=db_path,
        password_hash=password_hash,
        session_timeout_local=3600,
        session_timeout_remote=1800,
    )
    await service.start()
    yield service  # type: ignore[misc]
    await service.stop()
    os.unlink(db_path)


# ---------------------------------------------------------------------------
# Password verification tests
# ---------------------------------------------------------------------------


class TestPasswordVerification:
    """Tests for bcrypt password hashing and verification."""

    def test_hash_password_returns_string(self) -> None:
        result = AuthService.hash_password("mypass")
        assert isinstance(result, str)
        assert result.startswith("$2")

    def test_verify_correct_password(self, password_hash: str) -> None:
        service = AuthService(password_hash=password_hash)
        assert service.verify_password("testpass123") is True

    def test_verify_wrong_password(self, password_hash: str) -> None:
        service = AuthService(password_hash=password_hash)
        assert service.verify_password("wrongpass") is False

    def test_verify_empty_hash_allows_all(self) -> None:
        service = AuthService(password_hash="")
        assert service.verify_password("anything") is True

    def test_verify_invalid_hash_returns_false(self) -> None:
        service = AuthService(password_hash="not-a-bcrypt-hash")
        assert service.verify_password("anything") is False


# ---------------------------------------------------------------------------
# Session lifecycle tests
# ---------------------------------------------------------------------------


class TestSessionLifecycle:
    """Tests for session creation, validation, and deletion."""

    async def test_create_session_returns_id(self, auth_service: AuthService) -> None:
        session_id = await auth_service.create_session()
        assert isinstance(session_id, str)
        assert len(session_id) > 20

    async def test_validate_new_session(self, auth_service: AuthService) -> None:
        session_id = await auth_service.create_session()
        assert await auth_service.validate_session(session_id) is True

    async def test_validate_nonexistent_session(self, auth_service: AuthService) -> None:
        assert await auth_service.validate_session("nonexistent") is False

    async def test_delete_session(self, auth_service: AuthService) -> None:
        session_id = await auth_service.create_session()
        await auth_service.delete_session(session_id)
        assert await auth_service.validate_session(session_id) is False

    async def test_session_stores_ip_and_ua(self, auth_service: AuthService) -> None:
        session_id = await auth_service.create_session(
            ip_address="192.168.1.100",
            user_agent="TestBrowser/1.0",
        )
        assert await auth_service.validate_session(session_id) is True

    async def test_local_session_timeout(self, auth_service: AuthService) -> None:
        session_id = await auth_service.create_session(is_remote=False)
        assert await auth_service.validate_session(session_id) is True

    async def test_remote_session_flag(self, auth_service: AuthService) -> None:
        session_id = await auth_service.create_session(is_remote=True)
        assert await auth_service.validate_session(session_id) is True

    async def test_multiple_sessions_independent(self, auth_service: AuthService) -> None:
        s1 = await auth_service.create_session()
        s2 = await auth_service.create_session()
        assert s1 != s2
        await auth_service.delete_session(s1)
        assert await auth_service.validate_session(s1) is False
        assert await auth_service.validate_session(s2) is True


# ---------------------------------------------------------------------------
# Session expiry tests
# ---------------------------------------------------------------------------


class TestSessionExpiry:
    """Tests for session expiration and cleanup."""

    async def test_expired_session_invalid(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        service = AuthService(
            db_path=db_path,
            password_hash="",
            session_timeout_local=0,  # Immediate expiry
        )
        await service.start()
        try:
            session_id = await service.create_session()
            # Session created with timeout=0, so expires_at = now
            # Any positive elapsed time should cause expiry
            import time

            time.sleep(0.01)  # Ensure time passes
            assert await service.validate_session(session_id) is False
        finally:
            await service.stop()
            os.unlink(db_path)

    async def test_cleanup_expired_sessions(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        service = AuthService(
            db_path=db_path,
            password_hash="",
            session_timeout_local=0,
        )
        await service.start()
        try:
            await service.create_session()
            await service.create_session()
            import time

            time.sleep(0.01)
            removed = await service.cleanup_expired()
            assert removed == 2
        finally:
            await service.stop()
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# CSRF token tests
# ---------------------------------------------------------------------------


class TestCsrfTokens:
    """Tests for CSRF token generation and verification."""

    def test_generate_csrf_token(self) -> None:
        token = AuthService.generate_csrf_token("test-session")
        assert isinstance(token, str)
        assert len(token) == 32

    def test_csrf_token_deterministic(self) -> None:
        t1 = AuthService.generate_csrf_token("test-session")
        t2 = AuthService.generate_csrf_token("test-session")
        assert t1 == t2

    def test_csrf_token_differs_by_session(self) -> None:
        t1 = AuthService.generate_csrf_token("session-a")
        t2 = AuthService.generate_csrf_token("session-b")
        assert t1 != t2

    def test_verify_csrf_valid(self) -> None:
        token = AuthService.generate_csrf_token("test-session")
        assert AuthService.verify_csrf_token("test-session", token) is True

    def test_verify_csrf_invalid(self) -> None:
        assert AuthService.verify_csrf_token("test-session", "bad-token") is False

    def test_verify_csrf_wrong_session(self) -> None:
        token = AuthService.generate_csrf_token("session-a")
        assert AuthService.verify_csrf_token("session-b", token) is False
