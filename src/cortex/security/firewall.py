"""Firewall abstraction — nftables CLI wrapper with mock for testing.

NftablesFirewall wraps `nft` CLI commands. MockFirewall records rules in memory.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MockFirewall:
    """In-memory firewall mock for testing.

    Records rules as dicts without executing any system commands.
    """

    def __init__(self) -> None:
        self._rules: list[dict[str, str]] = []

    @property
    def rules(self) -> list[dict[str, str]]:
        return list(self._rules)

    def add_rule(self, direction: str, domain: str, action: str = "accept") -> None:
        """Add a firewall rule."""
        self._rules.append({"direction": direction, "domain": domain, "action": action})
        logger.debug("Mock firewall: added %s rule for %s (%s)", direction, domain, action)

    def delete_rule(self, direction: str, domain: str) -> bool:
        """Delete a firewall rule."""
        original_len = len(self._rules)
        self._rules = [
            r for r in self._rules if not (r["direction"] == direction and r["domain"] == domain)
        ]
        return len(self._rules) < original_len

    def flush(self) -> None:
        """Remove all firewall rules."""
        self._rules.clear()
        logger.debug("Mock firewall: flushed all rules")

    def list_rules(self) -> list[dict[str, str]]:
        """List all current rules."""
        return list(self._rules)


class NftablesFirewall:
    """Nftables firewall wrapper (requires root).

    Wraps `nft` CLI commands for managing firewall rules.
    Not used in testing — requires root privileges and nftables installed.
    """

    def __init__(self, table_name: str = "cortex") -> None:
        self._table_name = table_name

    def add_rule(self, direction: str, domain: str, action: str = "accept") -> None:
        """Add an nftables rule (stub — requires root)."""
        logger.warning(
            "NftablesFirewall.add_rule called but not implemented (requires root): %s %s %s",
            direction,
            domain,
            action,
        )

    def delete_rule(self, direction: str, domain: str) -> bool:
        """Delete an nftables rule (stub — requires root)."""
        logger.warning(
            "NftablesFirewall.delete_rule called but not implemented (requires root): %s %s",
            direction,
            domain,
        )
        return False

    def flush(self) -> None:
        """Flush all nftables rules (stub — requires root)."""
        logger.warning("NftablesFirewall.flush called but not implemented (requires root)")

    def list_rules(self) -> list[dict[str, Any]]:
        """List nftables rules (stub — requires root)."""
        return []
