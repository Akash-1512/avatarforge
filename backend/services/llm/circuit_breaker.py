"""Re-export shim — the circuit breaker now lives in services.common
so both LLM and TTS services share one implementation."""

from backend.services.common.circuit_breaker import CircuitBreaker, CircuitState

__all__ = ["CircuitBreaker", "CircuitState"]
