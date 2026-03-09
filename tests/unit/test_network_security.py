"""Tests for network security manager."""

from __future__ import annotations

from cortex.security.network import NetworkSecurityManager


class TestAllowlist:
    def test_add_to_allowlist(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.add_to_allowlist("example.com")
        assert "example.com" in mgr.allowlist

    def test_remove_from_allowlist(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.add_to_allowlist("example.com")
        mgr.remove_from_allowlist("example.com")
        assert "example.com" not in mgr.allowlist

    def test_case_normalization(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.add_to_allowlist("Example.COM")
        assert "example.com" in mgr.allowlist

    def test_whitespace_stripped(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.add_to_allowlist("  example.com  ")
        assert "example.com" in mgr.allowlist


class TestDenylist:
    def test_add_to_denylist(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.add_to_denylist("evil.com")
        assert "evil.com" in mgr.denylist

    def test_denylist_removes_from_allowlist(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.add_to_allowlist("example.com")
        mgr.add_to_denylist("example.com")
        assert "example.com" in mgr.denylist
        assert "example.com" not in mgr.allowlist

    def test_allowlist_removes_from_denylist(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.add_to_denylist("example.com")
        mgr.add_to_allowlist("example.com")
        assert "example.com" in mgr.allowlist
        assert "example.com" not in mgr.denylist


class TestIsAllowed:
    def test_disabled_allows_all(self) -> None:
        mgr = NetworkSecurityManager(enabled=False)
        assert mgr.is_allowed("anything.com") is True

    def test_allowlisted_allowed(self) -> None:
        mgr = NetworkSecurityManager(enabled=True, default_policy="deny")
        mgr.add_to_allowlist("example.com")
        assert mgr.is_allowed("example.com") is True

    def test_denylisted_denied(self) -> None:
        mgr = NetworkSecurityManager(enabled=True, default_policy="allow")
        mgr.add_to_denylist("evil.com")
        assert mgr.is_allowed("evil.com") is False

    def test_default_deny(self) -> None:
        mgr = NetworkSecurityManager(enabled=True, default_policy="deny")
        assert mgr.is_allowed("unknown.com") is False

    def test_default_allow(self) -> None:
        mgr = NetworkSecurityManager(enabled=True, default_policy="allow")
        assert mgr.is_allowed("unknown.com") is True


class TestProviderSync:
    def test_sync_endpoints(self) -> None:
        mgr = NetworkSecurityManager(enabled=True)
        mgr.sync_provider_endpoints(["api.openai.com", "calendar.google.com"])
        assert "api.openai.com" in mgr.allowlist
        assert "calendar.google.com" in mgr.allowlist


class TestGetRules:
    def test_get_rules(self) -> None:
        mgr = NetworkSecurityManager(enabled=True, default_policy="deny")
        mgr.add_to_allowlist("example.com")
        rules = mgr.get_rules()
        assert rules["enabled"] is True
        assert rules["default_policy"] == "deny"
        assert "example.com" in rules["allowlist"]
        assert rules["allowlist_count"] == 1
