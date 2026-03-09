"""Network security manager — domain allowlist and firewall rule management.

Manages which domains the system is allowed to contact. Provides integration
with nftables for hardware deployment (via MockFirewall for testing).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NetworkSecurityManager:
    """Manages network security with domain allowlist and firewall integration.

    Args:
        enabled: Whether network security is active.
        default_policy: Default policy for unlisted domains ("allow" or "deny").
        firewall: Firewall implementation (MockFirewall or NftablesFirewall).
    """

    def __init__(
        self,
        enabled: bool = False,
        default_policy: str = "deny",
        firewall: Any | None = None,
    ) -> None:
        self._enabled = enabled
        self._default_policy = default_policy
        self._firewall = firewall
        self._allowlist: set[str] = set()
        self._denylist: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def default_policy(self) -> str:
        return self._default_policy

    @property
    def allowlist(self) -> set[str]:
        return set(self._allowlist)

    @property
    def denylist(self) -> set[str]:
        return set(self._denylist)

    def add_to_allowlist(self, domain: str) -> None:
        """Add a domain to the allowlist."""
        domain = domain.strip().lower()
        self._allowlist.add(domain)
        self._denylist.discard(domain)
        logger.info("Added '%s' to network allowlist", domain)

    def remove_from_allowlist(self, domain: str) -> None:
        """Remove a domain from the allowlist."""
        domain = domain.strip().lower()
        self._allowlist.discard(domain)

    def add_to_denylist(self, domain: str) -> None:
        """Add a domain to the denylist."""
        domain = domain.strip().lower()
        self._denylist.add(domain)
        self._allowlist.discard(domain)

    def remove_from_denylist(self, domain: str) -> None:
        """Remove a domain from the denylist."""
        domain = domain.strip().lower()
        self._denylist.discard(domain)

    def is_allowed(self, domain: str) -> bool:
        """Check if a domain is allowed.

        Returns True if:
        - Security is disabled (everything allowed)
        - Domain is in allowlist
        - Domain is not in denylist AND default_policy is "allow"
        """
        if not self._enabled:
            return True

        domain = domain.strip().lower()

        if domain in self._denylist:
            return False
        if domain in self._allowlist:
            return True

        return self._default_policy == "allow"

    def sync_provider_endpoints(self, endpoints: list[str]) -> None:
        """Sync provider API endpoints into the allowlist.

        Used to automatically allow LLM provider, calendar, email, etc.
        """
        for endpoint in endpoints:
            self.add_to_allowlist(endpoint)

    def get_rules(self) -> dict[str, Any]:
        """Get the current security rules for display."""
        return {
            "enabled": self._enabled,
            "default_policy": self._default_policy,
            "allowlist": sorted(self._allowlist),
            "denylist": sorted(self._denylist),
            "allowlist_count": len(self._allowlist),
            "denylist_count": len(self._denylist),
        }
