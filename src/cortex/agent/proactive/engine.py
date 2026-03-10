"""Proactive engine — idle-time think loop for pattern-based suggestions.

Queries the pattern detector, generates candidates, and delivers via
the notification service. Opt-in, disabled by default.

M5.5 expansion: async run() loop, DataSources integration, morning
briefing trigger, memory consolidation trigger.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from cortex.agent.proactive.briefing import BriefingBuilder
from cortex.agent.proactive.consolidator import MemoryConsolidator
from cortex.agent.proactive.detector import PatternDetector
from cortex.agent.proactive.scheduler import ProactiveScheduler
from cortex.agent.proactive.sources import ProactiveDataSources
from cortex.agent.proactive.triggers import TriggerManager
from cortex.agent.proactive.types import ProactiveCandidate, ProactiveType, RoutinePattern

logger = logging.getLogger(__name__)


class ProactiveEngine:
    """Idle-time proactive intelligence engine.

    Runs a background think loop that:
    1. Detects routine patterns from episodic memory
    2. Generates proactive suggestions (candidates)
    3. Delivers them via the notification service
    4. Periodically consolidates memory
    5. Fires morning briefings at the configured time

    Args:
        detector: Pattern detector instance.
        enabled: Whether the engine is active.
        think_interval: Seconds between think cycles.
        notification_service: For delivering candidates.
        sources: Data sources aggregator.
        consolidator: Memory consolidator.
    """

    def __init__(
        self,
        detector: PatternDetector | None = None,
        enabled: bool = False,
        think_interval: float = 300.0,
        notification_service: Any = None,
        sources: ProactiveDataSources | None = None,
        consolidator: MemoryConsolidator | None = None,
    ) -> None:
        self._detector = detector or PatternDetector()
        self._enabled = enabled
        self._think_interval = think_interval
        self._last_think: float = 0.0
        self._candidates: list[ProactiveCandidate] = []
        self._delivered: list[ProactiveCandidate] = []

        # M5.5 additions
        self._notification_service = notification_service
        self._sources = sources or ProactiveDataSources()
        self._consolidator = consolidator or MemoryConsolidator()
        self._scheduler = ProactiveScheduler()
        self._triggers = TriggerManager()
        self._briefing_builder = BriefingBuilder()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._in_session = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def think_interval(self) -> float:
        return self._think_interval

    @property
    def candidates(self) -> list[ProactiveCandidate]:
        return list(self._candidates)

    @property
    def delivered(self) -> list[ProactiveCandidate]:
        return list(self._delivered)

    @property
    def scheduler(self) -> ProactiveScheduler:
        return self._scheduler

    @property
    def triggers(self) -> TriggerManager:
        return self._triggers

    @property
    def in_session(self) -> bool:
        return self._in_session

    @in_session.setter
    def in_session(self, value: bool) -> None:
        self._in_session = value

    @property
    def last_think(self) -> float:
        return self._last_think

    def should_think(self) -> bool:
        """Check if it's time for a think cycle."""
        if not self._enabled:
            return False
        return (time.time() - self._last_think) >= self._think_interval

    def generate_candidates(
        self,
        patterns: list[RoutinePattern],
        current_hour: int,
        current_day: int,
    ) -> list[ProactiveCandidate]:
        """Generate proactive candidates from detected patterns."""
        relevant = self._detector.filter_for_time(patterns, current_hour, current_day)
        candidates: list[ProactiveCandidate] = []

        for pattern in relevant:
            candidate = ProactiveCandidate(
                proactive_type=ProactiveType.ROUTINE_REMINDER,
                title=f"Routine: {pattern.content}",
                message=(
                    f"You usually use '{pattern.content}' around this time "
                    f"({pattern.count} times observed)."
                ),
                priority=3,
                pattern=pattern,
            )
            candidates.append(candidate)

        self._candidates = candidates
        self._last_think = time.time()
        return candidates

    def mark_delivered(self, candidate: ProactiveCandidate) -> None:
        """Mark a candidate as delivered."""
        self._delivered.append(candidate)
        if candidate in self._candidates:
            self._candidates.remove(candidate)

    def clear(self) -> None:
        """Clear all candidates and delivery history."""
        self._candidates.clear()
        self._delivered.clear()

    # --- M5.5: Async run loop ---

    async def start(
        self,
        morning_briefing_hour: int = 7,
        morning_briefing_minute: int = 0,
        morning_briefing_enabled: bool = False,
        consolidation_enabled: bool = False,
        consolidation_interval_minutes: int = 60,
    ) -> None:
        """Start the proactive engine background loop and scheduler."""
        self._running = True

        if morning_briefing_enabled:
            self._scheduler.add_daily(
                "morning_briefing",
                "Morning Briefing",
                morning_briefing_hour,
                morning_briefing_minute,
                self._deliver_morning_briefing,
            )

        if consolidation_enabled:
            self._scheduler.add_interval(
                "memory_consolidation",
                "Memory Consolidation",
                consolidation_interval_minutes * 60.0,
                self._run_consolidation,
            )

        await self._scheduler.start()

        if self._enabled:
            self._task = asyncio.create_task(self._think_loop())

        logger.info("ProactiveEngine started", extra={"enabled": self._enabled})

    async def stop(self) -> None:
        """Stop the engine and scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        await self._scheduler.stop()
        logger.info("ProactiveEngine stopped")

    async def _think_loop(self) -> None:
        """Background loop: detect patterns, generate candidates, deliver."""
        try:
            while self._running and self._enabled:
                await asyncio.sleep(self._think_interval)
                if not self._running:
                    break
                if self._in_session:
                    continue

                await self._run_think_cycle()
        except asyncio.CancelledError:
            pass

    async def _run_think_cycle(self) -> None:
        """Execute one think cycle."""
        try:
            patterns = await self._sources.get_patterns()
            now = datetime.now()  # noqa: DTZ005
            candidates = self.generate_candidates(
                patterns, now.hour, now.weekday(),
            )
            for candidate in candidates:
                await self.deliver_candidate(candidate)
        except Exception:
            logger.exception("Think cycle failed")

    async def deliver_candidate(self, candidate: ProactiveCandidate) -> bool:
        """Deliver a candidate via the notification service."""
        if self._notification_service is None:
            self.mark_delivered(candidate)
            return False
        try:
            from cortex.agent.notifications import Notification

            notification = Notification(
                id=uuid.uuid4().hex[:8],
                priority=candidate.priority,
                title=candidate.title,
                body=candidate.message,
                source="proactive",
            )
            delivered = await self._notification_service.notify(notification)
            self.mark_delivered(candidate)
            return bool(delivered)
        except Exception:
            logger.exception("Failed to deliver candidate")
            return False

    async def _deliver_morning_briefing(self) -> None:
        """Gather data and deliver morning briefing."""
        try:
            calendar_events = await self._sources.get_calendar_events()
            weather = await self._sources.get_weather()
            reminders = await self._sources.get_active_reminders()
            patterns = await self._sources.get_patterns()

            candidate = self._briefing_builder.build(
                calendar_events=calendar_events,
                reminders=reminders,
                patterns=patterns,
                weather=weather,
            )
            await self.deliver_candidate(candidate)
            logger.info("Morning briefing delivered")
        except Exception:
            logger.exception("Morning briefing failed")

    async def _run_consolidation(self) -> None:
        """Run memory consolidation."""
        if not self._consolidator.should_run():
            return
        try:
            recent = await self._sources.get_recent_events()
            facts = await self._consolidator.consolidate(recent)
            if facts:
                logger.info("Consolidated %d facts", len(facts))
        except Exception:
            logger.exception("Memory consolidation failed")

    def handle_event(
        self, event_type: str, event_data: dict[str, Any],
    ) -> list[ProactiveCandidate]:
        """Evaluate triggers against an incoming event."""
        result = self._triggers.evaluate(event_type, event_data)
        self._candidates.extend(result.candidates)
        return result.candidates
