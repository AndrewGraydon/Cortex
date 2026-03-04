"""Authentication service — bcrypt password verification + SQLite sessions.

Sessions are server-side (SQLite), referenced by HTTP-only cookie.
Password hash comes from CORTEX_PASSWORD_HASH env var or config.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time

import aiosqlite
import bcrypt as _bcrypt

logger = logging.getLogger(__name__)

SESSION_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'primary',
    created_at REAL NOT NULL,
    last_accessed REAL NOT NULL,
    expires_at REAL NOT NULL,
    is_remote BOOLEAN NOT NULL DEFAULT 0,
    ip_address TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
"""


class AuthService:
    """Manages password verification and session lifecycle."""

    def __init__(
        self,
        db_path: str = "data/cortex.db",
        password_hash: str = "",
        session_timeout_local: int = 3600,
        session_timeout_remote: int = 1800,
    ) -> None:
        self._db_path = db_path
        self._password_hash = password_hash or os.environ.get("CORTEX_PASSWORD_HASH", "")
        self._session_timeout_local = session_timeout_local
        self._session_timeout_remote = session_timeout_remote
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        """Open database and create sessions table."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(SESSION_SCHEMA)
        await self._db.commit()
        logger.info("Auth service started (db=%s)", self._db_path)

    async def stop(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    def verify_password(self, password: str) -> bool:
        """Check a plaintext password against the stored bcrypt hash."""
        if not self._password_hash:
            logger.warning("No password hash configured — authentication disabled")
            return True
        try:
            return _bcrypt.checkpw(
                password.encode("utf-8"),
                self._password_hash.encode("utf-8"),
            )
        except Exception:
            logger.exception("Password verification failed")
            return False

    @staticmethod
    def hash_password(password: str) -> str:
        """Generate a bcrypt hash for a password (for setup scripts)."""
        salt = _bcrypt.gensalt()
        return _bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    async def create_session(
        self,
        ip_address: str = "",
        user_agent: str = "",
        is_remote: bool = False,
    ) -> str:
        """Create a new session and return the session ID."""
        assert self._db is not None
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        timeout = self._session_timeout_remote if is_remote else self._session_timeout_local
        expires_at = now + timeout

        await self._db.execute(
            "INSERT INTO sessions (session_id, user_id, created_at, last_accessed, "
            "expires_at, is_remote, ip_address, user_agent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, "primary", now, now, expires_at, is_remote, ip_address, user_agent),
        )
        await self._db.commit()
        logger.info("Session created: remote=%s, ip=%s", is_remote, ip_address)
        return session_id

    async def validate_session(self, session_id: str) -> bool:
        """Check if a session is valid and not expired. Updates last_accessed."""
        if not self._db:
            return False
        now = time.time()
        async with self._db.execute(
            "SELECT expires_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return False

        expires_at = row[0]
        if now > expires_at:
            await self.delete_session(session_id)
            return False

        # Touch last_accessed
        await self._db.execute(
            "UPDATE sessions SET last_accessed = ? WHERE session_id = ?",
            (now, session_id),
        )
        await self._db.commit()
        return True

    async def delete_session(self, session_id: str) -> None:
        """Remove a session (logout)."""
        if not self._db:
            return
        await self._db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await self._db.commit()

    async def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        if not self._db:
            return 0
        now = time.time()
        cursor = await self._db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        await self._db.commit()
        return cursor.rowcount

    @staticmethod
    def generate_csrf_token(session_id: str) -> str:
        """Generate a CSRF token derived from the session ID.

        Uses HMAC-like derivation so the token is tied to the session
        but not reversible to the session ID.
        """
        secret = os.environ.get("CORTEX_SECRET_KEY", "cortex-dev-secret")
        return hashlib.sha256(f"{secret}:{session_id}".encode()).hexdigest()[:32]

    @staticmethod
    def verify_csrf_token(session_id: str, token: str) -> bool:
        """Verify a CSRF token matches the expected value for this session."""
        expected = AuthService.generate_csrf_token(session_id)
        return secrets.compare_digest(expected, token)
