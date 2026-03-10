"""Tests for secret key validation — dev default warning."""

from __future__ import annotations

from unittest.mock import patch

from cortex.web.auth import AuthService


class TestSecretKeyCheck:
    """check_secret_key() behavior."""

    def test_dev_default_returns_false(self) -> None:
        with patch.dict("os.environ", {"CORTEX_SECRET_KEY": "cortex-dev-secret"}):
            assert AuthService.check_secret_key() is False

    def test_no_env_var_returns_false(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert AuthService.check_secret_key() is False

    def test_custom_key_returns_true(self) -> None:
        with patch.dict("os.environ", {"CORTEX_SECRET_KEY": "my-secure-production-key"}):
            assert AuthService.check_secret_key() is True

    def test_csrf_token_uses_env_key(self) -> None:
        with patch.dict("os.environ", {"CORTEX_SECRET_KEY": "key-a"}):
            token_a = AuthService.generate_csrf_token("session1")
        with patch.dict("os.environ", {"CORTEX_SECRET_KEY": "key-b"}):
            token_b = AuthService.generate_csrf_token("session1")
        assert token_a != token_b

    def test_csrf_verify_with_matching_key(self) -> None:
        with patch.dict("os.environ", {"CORTEX_SECRET_KEY": "test-key"}):
            token = AuthService.generate_csrf_token("session1")
            assert AuthService.verify_csrf_token("session1", token) is True
