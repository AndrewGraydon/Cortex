"""Tests for log redactor — password/token/key redaction."""

from __future__ import annotations

from cortex.security.log_redactor import log_redactor, redact_string, redact_value


class TestRedactString:
    """String-level redaction."""

    def test_redacts_password_equals(self) -> None:
        assert "[REDACTED]" in redact_string("password=secret123")

    def test_redacts_password_colon(self) -> None:
        assert "[REDACTED]" in redact_string("password: mysecret")

    def test_redacts_api_key(self) -> None:
        assert "[REDACTED]" in redact_string("api_key=sk-12345678")

    def test_redacts_apikey(self) -> None:
        assert "[REDACTED]" in redact_string("apikey=abcdefgh12345")

    def test_redacts_bearer_token(self) -> None:
        result = redact_string("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
        assert "eyJ" not in result
        assert "[REDACTED]" in result

    def test_redacts_session_id(self) -> None:
        assert "[REDACTED]" in redact_string("session_id=abc123def456ghi789")

    def test_redacts_generic_token(self) -> None:
        assert "[REDACTED]" in redact_string("token=my-secret-token-value")

    def test_redacts_secret(self) -> None:
        assert "[REDACTED]" in redact_string("secret=long-secret-value")

    def test_redacts_bcrypt_hash(self) -> None:
        bcrypt_hash = "$2b$12$LJ3m4/8sBdF4RnN.3YTGYe1234567890123456789012345678901"
        assert "[BCRYPT_HASH]" in redact_string(bcrypt_hash)

    def test_preserves_normal_text(self) -> None:
        text = "User logged in from 192.168.1.100"
        assert redact_string(text) == text

    def test_preserves_non_sensitive_values(self) -> None:
        text = "status=healthy uptime=3600"
        assert redact_string(text) == text


class TestRedactValue:
    """Recursive value redaction."""

    def test_redacts_string(self) -> None:
        assert "[REDACTED]" in redact_value("password=test")

    def test_redacts_dict_values(self) -> None:
        result = redact_value({"msg": "password=secret"})
        assert "[REDACTED]" in result["msg"]

    def test_redacts_list_values(self) -> None:
        result = redact_value(["password=abc", "ok text"])
        assert "[REDACTED]" in result[0]
        assert result[1] == "ok text"

    def test_passes_through_non_string(self) -> None:
        assert redact_value(42) == 42
        assert redact_value(3.14) == 3.14
        assert redact_value(None) is None
        assert redact_value(True) is True


class TestLogRedactorProcessor:
    """Structlog processor integration."""

    def test_redacts_event(self) -> None:
        event_dict = {"event": "Login with password=secret123"}
        result = log_redactor(None, "info", event_dict)
        assert "[REDACTED]" in result["event"]
        assert "secret123" not in result["event"]

    def test_redacts_extra_fields(self) -> None:
        event_dict = {"event": "Login attempt", "token": "token=abc12345678"}
        result = log_redactor(None, "info", event_dict)
        assert "[REDACTED]" in result["token"]

    def test_preserves_non_sensitive_event(self) -> None:
        event_dict = {"event": "Health check passed", "status": "healthy"}
        result = log_redactor(None, "info", event_dict)
        assert result["event"] == "Health check passed"
        assert result["status"] == "healthy"

    def test_preserves_internal_keys(self) -> None:
        event_dict = {
            "event": "test",
            "_record": "password=secret",
            "_from_structlog": True,
        }
        result = log_redactor(None, "info", event_dict)
        # Internal keys should not be redacted
        assert result["_record"] == "password=secret"
