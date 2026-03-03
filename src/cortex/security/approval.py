"""Button-driven approval flow for Tier 2-3 actions.

Shows action description on display, waits for button gesture:
  - SINGLE_CLICK → approve
  - LONG_PRESS → deny
  - Timeout → deny (default_deny_on_timeout)

Integrates with existing ButtonStateMachine and DisplayService.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cortex.hal.types import ButtonGesture, DisplayState
from cortex.security.types import ApprovalRequest, ApprovalStatus

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Manages user approval flow via button gestures and display.

    The display shows the action description with instructions.
    The button service provides gesture events for approval/denial.

    Args:
        display: Display service (or mock) with set_state/show_text.
        button: Button service (or mock) with wait_gesture.
        timeout_seconds: Default timeout for approval requests.
        default_deny_on_timeout: If True, timeout results in denial.
    """

    def __init__(
        self,
        display: Any = None,
        button: Any = None,
        timeout_seconds: float = 60.0,
        default_deny_on_timeout: bool = True,
    ) -> None:
        self._display = display
        self._button = button
        self.timeout_seconds = timeout_seconds
        self._default_deny_on_timeout = default_deny_on_timeout
        self._pending: ApprovalRequest | None = None
        self._history: list[tuple[ApprovalRequest, ApprovalStatus]] = []

    @property
    def pending(self) -> ApprovalRequest | None:
        """The currently pending approval request, if any."""
        return self._pending

    @property
    def history(self) -> list[tuple[ApprovalRequest, ApprovalStatus]]:
        """History of approval requests and their outcomes."""
        return list(self._history)

    async def request_approval(self, request: ApprovalRequest) -> ApprovalStatus:
        """Show approval prompt and wait for user response.

        Returns the approval status (approved, denied, or timeout).
        """
        self._pending = request
        timeout = request.timeout_seconds or self.timeout_seconds

        try:
            # Show approval prompt on display
            await self._show_prompt(request)

            # Wait for button gesture
            status = await self._wait_for_response(timeout)

            self._history.append((request, status))
            logger.info(
                "Approval %s for %s: %s",
                request.request_id,
                request.action_id,
                status.value,
            )
            return status

        except Exception:
            logger.exception("Error during approval flow for %s", request.action_id)
            status = ApprovalStatus.TIMEOUT
            self._history.append((request, status))
            return status

        finally:
            self._pending = None
            # Restore display to previous state
            await self._clear_prompt()

    async def _show_prompt(self, request: ApprovalRequest) -> None:
        """Display the approval prompt."""
        if self._display is None:
            return
        text = f"Approve: {request.action_description}?\nClick=Yes  Hold=No"
        if hasattr(self._display, "set_state"):
            await self._display.set_state(DisplayState.ALERT, text)

    async def _clear_prompt(self) -> None:
        """Clear the approval prompt from display."""
        if self._display is None:
            return
        if hasattr(self._display, "set_state"):
            await self._display.set_state(DisplayState.IDLE)

    async def _wait_for_response(self, timeout: float) -> ApprovalStatus:
        """Wait for a button gesture within the timeout."""
        if self._button is None:
            logger.warning("No button service — auto-denying approval")
            return (
                ApprovalStatus.TIMEOUT
                if self._default_deny_on_timeout
                else ApprovalStatus.USER_APPROVED
            )

        try:
            event = await asyncio.wait_for(
                self._button.wait_gesture(),
                timeout=timeout,
            )
            if event.gesture == ButtonGesture.SINGLE_CLICK:
                return ApprovalStatus.USER_APPROVED
            if event.gesture == ButtonGesture.LONG_PRESS:
                return ApprovalStatus.USER_DENIED
            # Any other gesture — treat as denial
            logger.debug("Unexpected gesture during approval: %s", event.gesture.value)
            return ApprovalStatus.USER_DENIED

        except TimeoutError:
            logger.info("Approval timed out after %.1fs", timeout)
            return ApprovalStatus.TIMEOUT

    async def handle_gesture_while_pending(self, gesture: ButtonGesture) -> bool:
        """Handle a button gesture when an approval is pending.

        Returns True if the gesture was consumed by the approval flow.
        Used by the voice pipeline to route gestures appropriately.
        """
        return self._pending is not None
