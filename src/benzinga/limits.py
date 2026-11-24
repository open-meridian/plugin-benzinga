"""How fast the plugin asks Benzinga, and how it backs off.

Benzinga's allowance depends on each firm's plan, and its documentation
states no number. The plugin keeps to the `benzinga_requests_per_second`
setting, 1 to 10, 2 by default: set it within your plan's limit.

**The pace.** Requests are spaced evenly, one every `1/rate` of a second,
counted in whole nanoseconds and rounded up, so any one second holds at most
`rate` of them. One request goes at a time (a lock), so two tasks never
share a slot.

**Backing off.** A 429 pauses every request: for as long as Benzinga's
`Retry-After` says where it says, otherwise 10 seconds, doubled after each
refusal in a row up to 10 minutes. The refused request is not sent again
here: what asked for it reads it on its next turn. The first answer that is
not a refusal resets the pause.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable

#: The most the setting allows.
MOST_PER_SECOND = 10
#: The rate by default.
DEFAULT_PER_SECOND = 2
#: The first pause after a refusal, and the longest, in seconds.
FIRST_PAUSE = 10.0
LONGEST_PAUSE = 600.0
#: The status Benzinga refuses an over-eager client with.
REFUSALS = (429,)


def per_second(asked: int) -> int:
    """The rate kept: the setting, held to 1 to 10."""
    return max(1, min(MOST_PER_SECOND, int(asked)))


def retry_after(value: str | None) -> float | None:
    """The seconds a `Retry-After` header says, where it gives a delay."""
    said = (value or "").strip()
    return float(said) if said.isdigit() else None


class Limiter:
    """At most `rate` requests a second, one at a time, and a pause after a
    refusal. `clock` answers nanoseconds and `sleep` waits seconds, both the
    real ones unless a test gives its own."""

    def __init__(
        self,
        rate: int = DEFAULT_PER_SECOND,
        clock: Callable[[], int] = time.monotonic_ns,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.clock = clock
        self.sleep = sleep
        self.rate = per_second(rate)
        self._lock = asyncio.Lock()
        self._next_ns = 0
        self._paused_until_ns = 0
        self._pause = FIRST_PAUSE
        #: Refusals seen since start, for the Connection page.
        self.refused = 0

    @property
    def spacing_ns(self) -> int:
        return math.ceil(1_000_000_000 / self.rate)

    def set_rate(self, rate: int) -> None:
        self.rate = per_second(rate)

    @property
    def paused_until_ns(self) -> int:
        return self._paused_until_ns

    async def wait(self) -> None:
        """Wait for this request's slot, and take it."""
        async with self._lock:
            now = self.clock()
            at = max(now, self._next_ns, self._paused_until_ns)
            if at > now:
                await self.sleep((at - now) / 1e9)
            self._next_ns = at + self.spacing_ns

    def answered(self, status: int, retry_after_seconds: float | None = None) -> None:
        """Note what Benzinga answered: a refusal pauses every request, anything
        else ends the pause."""
        if status not in REFUSALS:
            self._pause = FIRST_PAUSE
            return
        self.refused += 1
        pause = retry_after_seconds if retry_after_seconds is not None else self._pause
        self._paused_until_ns = max(self._paused_until_ns, self.clock() + int(pause * 1e9))
        self._pause = min(LONGEST_PAUSE, self._pause * 2)
