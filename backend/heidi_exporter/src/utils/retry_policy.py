"""Exponential-backoff retry tracker for per-session failures.

Usage::

    policy = RetryPolicy(max_attempts=3, base_delay=5.0, backoff_factor=6.0)
    sid = "abc123"

    while policy.should_retry(sid):
        policy.record_attempt(sid)
        wait = policy.delay_for(sid)
        time.sleep(wait)
        try:
            process(sid)
            break
        except Exception:
            pass  # loop will retry or exit when max_attempts hit

"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RetryPolicy:
    """Tracks per-session retry attempts and computes exponential wait times.

    Args:
        max_attempts:  Maximum number of total attempts (first try + retries).
        base_delay:    Seconds to wait before the 2nd attempt.
        backoff_factor: Multiplier applied for each subsequent attempt.
                        delay = base_delay * backoff_factor ** (attempt - 1)
                        e.g. base=5, factor=6 => 5s, 30s, 180s
    """

    max_attempts: int = 3
    base_delay: float = 5.0
    backoff_factor: float = 6.0
    _attempts: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def attempts(self, session_id: str) -> int:
        """Return how many attempts have been recorded for this session."""
        return self._attempts.get(session_id, 0)

    def should_retry(self, session_id: str) -> bool:
        """Return True if another attempt is allowed."""
        return self._attempts.get(session_id, 0) < self.max_attempts

    def record_attempt(self, session_id: str) -> None:
        """Increment the attempt counter for a session."""
        self._attempts[session_id] = self._attempts.get(session_id, 0) + 1

    def delay_for(self, session_id: str) -> float:
        """Seconds to wait before the next attempt (0 on the first attempt)."""
        n = self._attempts.get(session_id, 0)
        if n <= 1:
            return 0.0
        return self.base_delay * (self.backoff_factor ** (n - 2))

    def sleep_before_retry(self, session_id: str, logger=None) -> None:
        """Sleep for the computed backoff delay, logging the wait if a logger is given."""
        wait = self.delay_for(session_id)
        if wait > 0:
            if logger:
                logger.info(
                    "[RETRY] Session %s — attempt %d/%d, waiting %.0fs before retry",
                    session_id,
                    self._attempts.get(session_id, 1),
                    self.max_attempts,
                    wait,
                )
            time.sleep(wait)

    def exhausted(self, session_id: str) -> bool:
        """Return True once max_attempts have been recorded and no more retries allowed."""
        return self._attempts.get(session_id, 0) >= self.max_attempts
