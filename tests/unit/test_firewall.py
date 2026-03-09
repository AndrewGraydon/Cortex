"""Tests for firewall abstraction."""

from __future__ import annotations

from cortex.security.firewall import MockFirewall, NftablesFirewall


class TestMockFirewall:
    def test_add_rule(self) -> None:
        fw = MockFirewall()
        fw.add_rule("outbound", "example.com", "accept")
        assert len(fw.rules) == 1
        assert fw.rules[0]["domain"] == "example.com"

    def test_delete_rule(self) -> None:
        fw = MockFirewall()
        fw.add_rule("outbound", "example.com", "accept")
        deleted = fw.delete_rule("outbound", "example.com")
        assert deleted is True
        assert len(fw.rules) == 0

    def test_delete_nonexistent(self) -> None:
        fw = MockFirewall()
        deleted = fw.delete_rule("outbound", "nope.com")
        assert deleted is False

    def test_flush(self) -> None:
        fw = MockFirewall()
        fw.add_rule("outbound", "a.com")
        fw.add_rule("outbound", "b.com")
        fw.flush()
        assert len(fw.rules) == 0

    def test_list_rules(self) -> None:
        fw = MockFirewall()
        fw.add_rule("outbound", "a.com")
        fw.add_rule("inbound", "b.com", "drop")
        rules = fw.list_rules()
        assert len(rules) == 2

    def test_multiple_rules_different_directions(self) -> None:
        fw = MockFirewall()
        fw.add_rule("outbound", "example.com")
        fw.add_rule("inbound", "example.com")
        assert len(fw.rules) == 2


class TestNftablesFirewall:
    def test_instantiate(self) -> None:
        fw = NftablesFirewall()
        assert fw is not None

    def test_list_rules_empty(self) -> None:
        fw = NftablesFirewall()
        assert fw.list_rules() == []

    def test_delete_returns_false(self) -> None:
        fw = NftablesFirewall()
        assert fw.delete_rule("outbound", "x.com") is False
