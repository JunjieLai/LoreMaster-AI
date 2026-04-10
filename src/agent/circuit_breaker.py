"""
LoreMaster-AI - Circuit Breaker

Protects Pinecone and Neo4j from cascading failures.
After 3 consecutive failures, opens the circuit and returns degraded results immediately
instead of hanging for 10-30s on timeouts.

State machine: CLOSED → (3 failures) → OPEN → (60s) → HALF_OPEN → (success) → CLOSED
                                                                    → (failure) → OPEN

Inspired by: Claude Code autoCompact.ts — MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES=3,
stops retrying after repeated failures to avoid wasting API calls.
"""

import logging
import time
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast, not calling service
    HALF_OPEN = "half_open" # Testing if service recovered


class CircuitOpenError(Exception):
    """Raised when a circuit is OPEN and the call is rejected immediately."""
    def __init__(self, name: str):
        super().__init__(f"Circuit '{name}' is OPEN — service unavailable")
        self.circuit_name = name


class CircuitBreaker:
    """
    Single circuit breaker instance for one external service.

    Usage:
        cb = CircuitBreaker("pinecone")
        try:
            result = cb.call(pinecone_index.query, **params)
        except CircuitOpenError:
            # use fallback
        except Exception as e:
            # real error, circuit may have tripped
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = CircuitState.CLOSED

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if (time.time() - self._last_failure_time) >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit '%s': OPEN → HALF_OPEN (testing recovery)", self.name)
        return self._state

    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Call func(*args, **kwargs) through the circuit breaker.
        Raises CircuitOpenError if OPEN.
        """
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(self.name)

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as e:
            self._on_failure(e)
            raise

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            logger.info("Circuit '%s': HALF_OPEN → CLOSED (recovered)", self.name)
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self, exc: Exception):
        self._failure_count += 1
        self._last_failure_time = time.time()
        logger.warning(
            "Circuit '%s': failure %d/%d — %s",
            self.name, self._failure_count, self.failure_threshold, exc,
        )
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.error(
                "Circuit '%s': CLOSED → OPEN (threshold reached, recovery in %ds)",
                self.name, int(self.recovery_timeout),
            )

    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure": self._last_failure_time,
        }
