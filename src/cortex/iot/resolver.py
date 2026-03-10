"""Device resolver — natural language device name resolution.

Maps user utterances like "kitchen lights" to device IDs using
3-tier matching: exact name → fuzzy token → category+room.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from cortex.iot.registry import DeviceRegistry
from cortex.iot.types import DeviceCategory, DeviceInfo

logger = structlog.get_logger()

# Common aliases for device categories
_CATEGORY_ALIASES: dict[str, DeviceCategory] = {
    "light": DeviceCategory.LIGHT,
    "lights": DeviceCategory.LIGHT,
    "lamp": DeviceCategory.LIGHT,
    "lamps": DeviceCategory.LIGHT,
    "bulb": DeviceCategory.LIGHT,
    "switch": DeviceCategory.SWITCH,
    "switches": DeviceCategory.SWITCH,
    "plug": DeviceCategory.SWITCH,
    "plugs": DeviceCategory.SWITCH,
    "outlet": DeviceCategory.SWITCH,
    "sensor": DeviceCategory.SENSOR,
    "sensors": DeviceCategory.SENSOR,
    "thermostat": DeviceCategory.CLIMATE,
    "climate": DeviceCategory.CLIMATE,
    "heating": DeviceCategory.CLIMATE,
    "ac": DeviceCategory.CLIMATE,
    "cover": DeviceCategory.COVER,
    "blind": DeviceCategory.COVER,
    "blinds": DeviceCategory.COVER,
    "curtain": DeviceCategory.COVER,
    "curtains": DeviceCategory.COVER,
    "lock": DeviceCategory.LOCK,
    "locks": DeviceCategory.LOCK,
    "fan": DeviceCategory.FAN,
    "fans": DeviceCategory.FAN,
}


@dataclass(frozen=True)
class ResolveCandidate:
    """A device match candidate with confidence score."""

    device: DeviceInfo
    confidence: float  # 0.0 - 1.0
    match_type: str  # "exact", "fuzzy", "category_room"


@dataclass
class ResolveResult:
    """Result of device name resolution."""

    candidates: list[ResolveCandidate] = field(default_factory=list)
    ambiguous: bool = False

    @property
    def best(self) -> DeviceInfo | None:
        """Return the best candidate, or None if no match."""
        if not self.candidates:
            return None
        return self.candidates[0].device

    @property
    def matched(self) -> bool:
        return len(self.candidates) > 0 and not self.ambiguous


class DeviceResolver:
    """Resolves natural language device references to device IDs.

    3-tier matching:
    1. Exact name match (confidence 1.0)
    2. Fuzzy token intersection (confidence 0.5-0.9)
    3. Category + room match (confidence 0.3-0.7)
    """

    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry

    def resolve(self, query: str) -> ResolveResult:
        """Resolve a natural language device reference.

        Args:
            query: User utterance like "kitchen lights" or "bedroom lamp".

        Returns:
            ResolveResult with ranked candidates.
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return ResolveResult()

        tokens = query_lower.split()
        all_devices = self._registry.get_all()

        candidates: list[ResolveCandidate] = []

        # Tier 1: Exact name match
        for device in all_devices:
            if (
                query_lower == device.name.lower()
                or query_lower == device.friendly_name.lower()
                or query_lower == device.id.lower()
            ):
                candidates.append(ResolveCandidate(
                    device=device, confidence=1.0, match_type="exact",
                ))

        if candidates:
            return ResolveResult(candidates=candidates)

        # Tier 2: Fuzzy token intersection
        for device in all_devices:
            device_tokens = set(
                device.name.lower().split()
                + device.friendly_name.lower().split()
            )
            if device.room:
                device_tokens.update(device.room.lower().split())

            overlap = set(tokens) & device_tokens
            if overlap:
                confidence = len(overlap) / max(len(tokens), len(device_tokens))
                confidence = min(0.9, max(0.5, confidence))
                candidates.append(ResolveCandidate(
                    device=device, confidence=confidence, match_type="fuzzy",
                ))

        if candidates:
            candidates.sort(key=lambda c: c.confidence, reverse=True)
            ambiguous = (
                len(candidates) > 1
                and candidates[0].confidence - candidates[1].confidence < 0.1
            )
            return ResolveResult(candidates=candidates, ambiguous=ambiguous)

        # Tier 3: Category + room
        category = None
        room = None

        for token in tokens:
            if token in _CATEGORY_ALIASES:
                category = _CATEGORY_ALIASES[token]
            else:
                room = token

        if category is not None:
            category_devices = self._registry.get_by_category(category)
            if room:
                room_filtered = [
                    d for d in category_devices
                    if room in d.room.lower()
                ]
                if room_filtered:
                    category_devices = room_filtered

            for device in category_devices:
                confidence = 0.7 if room else 0.3
                candidates.append(ResolveCandidate(
                    device=device, confidence=confidence, match_type="category_room",
                ))

        if candidates:
            candidates.sort(key=lambda c: c.confidence, reverse=True)
            ambiguous = len(candidates) > 1 and not room
            return ResolveResult(candidates=candidates, ambiguous=ambiguous)

        return ResolveResult()
