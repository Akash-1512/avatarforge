"""In-memory circuit breaker per provider.

States: CLOSED (normal) → OPEN (after N consecutive failures, all calls
skipped) → HALF_OPEN (after recovery timeout, one trial call allowed).
A success in HALF_OPEN closes the circuit; a failure re-opens it.
"""

import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout_sec: float = 300.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if time.monotonic() - self._opened_at >= self.recovery_timeout_sec:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def allow_request(self) -> bool:
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
