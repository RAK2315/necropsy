"""Deadline and shared closure-check cap for one Engine run."""

from __future__ import annotations

import time
from typing import Callable, Optional


class Budget:
    """One Budget is created per run and shared by every phase."""

    def __init__(
        self,
        deadline_seconds: float,
        cap: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._end = clock() + deadline_seconds
        self._clock = clock
        self.cap = cap
        self.checks = 0

    def stop_reason(self) -> Optional[str]:
        """Return a termination reason, testing the deadline before the cap."""
        if self._clock() >= self._end:
            return "deadline_exceeded"
        if self.checks >= self.cap:
            return "search_cap_exceeded"
        return None

    def charge(self) -> Optional[str]:
        """Call immediately before a closure check. Counts it only if allowed."""
        reason = self.stop_reason()
        if reason is None:
            self.checks += 1
        return reason
