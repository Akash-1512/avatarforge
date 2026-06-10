"""Circuit breaker state machine — pure unit tests, no I/O."""

from backend.services.llm.circuit_breaker import CircuitBreaker, CircuitState


def test_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request()


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_sec=300)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert not cb.allow_request()


def test_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_half_open_after_recovery_timeout():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_sec=0.01)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    import time

    time.sleep(0.02)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request()


def test_half_open_success_closes_circuit():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_sec=0.01)
    cb.record_failure()
    import time

    time.sleep(0.02)
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
