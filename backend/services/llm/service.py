"""LLMService — multi-provider orchestration with fallback and circuit breaking.

Provider order is Azure OpenAI first, OpenAI second. Each provider has its
own circuit breaker: 3 consecutive failures open the circuit for 5 minutes,
during which the provider is skipped entirely (no wasted latency).
Every call — success or failure — is recorded to the token_usage table.
DB unavailability never fails a user request: usage recording is best-effort.
"""

import json
import time
from functools import lru_cache
from typing import Awaitable, Callable, List, Optional

from pydantic import ValidationError

from backend.config import get_settings
from backend.models.schemas import ScriptPayload, ScriptRequest, ScriptResponse, TokenUsageInfo
from backend.observability import lf
from backend.observability.logging import get_logger
from backend.services.llm.base import AllProvidersFailedError, BaseLLMProvider, LLMProviderError
from backend.services.llm.circuit_breaker import CircuitBreaker
from backend.services.llm.prompts import SCRIPT_SYSTEM_PROMPT, build_script_user_prompt
from backend.services.llm.providers import AzureOpenAIProvider, OpenAIProvider

logger = get_logger(__name__)

# USD per 1M tokens (input, output) — used for cost attribution, not billing
_PRICE_MAP = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

UsageRecorder = Callable[[dict], Awaitable[None]]


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    for key, (in_price, out_price) in _PRICE_MAP.items():
        if key in model:
            return round((prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000, 6)
    return 0.0


class LLMService:
    def __init__(
        self,
        providers: List[BaseLLMProvider],
        usage_recorder: Optional[UsageRecorder] = None,
        failure_threshold: int = 3,
        recovery_timeout_sec: float = 300.0,
    ):
        self.providers = providers
        self.usage_recorder = usage_recorder
        self.breakers = {
            p.name: CircuitBreaker(failure_threshold, recovery_timeout_sec) for p in providers
        }

    async def _record(self, payload: dict) -> None:
        if self.usage_recorder is None:
            return
        try:
            await self.usage_recorder(payload)
        except Exception as exc:  # noqa: BLE001 — usage recording is best-effort
            logger.warning("usage_record_failed", error=str(exc))

    async def complete_json_raw(self, system_prompt: str, user_prompt: str) -> str:
        """Provider-failover JSON completion for auxiliary tasks (e.g. LLM-as-Judge).

        Same fallback and circuit-breaker path as script generation, but
        returns the raw JSON string and lets the caller validate shape.
        """
        last_error: Exception | None = None
        for provider in self.providers:
            breaker = self.breakers[provider.name]
            if not breaker.allow_request():
                continue
            try:
                result = await provider.complete_json(system_prompt, user_prompt)
                breaker.record_success()
                return result.content
            except Exception as exc:  # noqa: BLE001 — try next provider
                breaker.record_failure()
                last_error = exc
                logger.warning(
                    "judge_provider_failed", provider=provider.name, error=str(exc)[:200]
                )
        raise AllProvidersFailedError(f"All providers failed: {last_error}")

    async def generate_script(self, request: ScriptRequest) -> ScriptResponse:
        user_prompt = build_script_user_prompt(
            request.topic,
            request.tone,
            request.duration_seconds,
            request.language,
            request.audience,
        )
        last_error: Exception | None = None

        for provider in self.providers:
            if not provider.available:
                logger.info("provider_skipped_unconfigured", provider=provider.name)
                continue

            breaker = self.breakers[provider.name]
            if not breaker.allow_request():
                logger.warning("provider_skipped_circuit_open", provider=provider.name)
                continue

            started = time.monotonic()
            try:
                result = await provider.complete_json(SCRIPT_SYSTEM_PROMPT, user_prompt)
                payload = ScriptPayload.model_validate(json.loads(result.content))
                latency_ms = int((time.monotonic() - started) * 1000)
                breaker.record_success()

                cost = estimate_cost_usd(
                    result.model, result.prompt_tokens, result.completion_tokens
                )
                await self._record(
                    {
                        "provider": provider.name,
                        "model": result.model,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                        "total_tokens": result.prompt_tokens + result.completion_tokens,
                        "estimated_cost_usd": cost,
                        "latency_ms": latency_ms,
                        "success": True,
                        "error_type": None,
                    }
                )
                logger.info(
                    "script_generated",
                    provider=provider.name,
                    model=result.model,
                    latency_ms=latency_ms,
                    segments=len(payload.segments),
                )
                lf.record_generation(
                    name="generate_script",
                    model=result.model,
                    provider=provider.name,
                    input_text=request.topic,
                    output_text=payload.title,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    latency_ms=latency_ms,
                    success=True,
                )
                return ScriptResponse(
                    title=payload.title,
                    segments=payload.segments,
                    total_duration_sec=payload.total_duration_sec,
                    provider_used=provider.name,
                    model=result.model,
                    latency_ms=latency_ms,
                    usage=TokenUsageInfo(
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        total_tokens=result.prompt_tokens + result.completion_tokens,
                        estimated_cost_usd=cost,
                    ),
                )

            except (LLMProviderError, json.JSONDecodeError, ValidationError) as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                breaker.record_failure()
                last_error = exc
                await self._record(
                    {
                        "provider": provider.name,
                        "model": "unknown",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "estimated_cost_usd": 0.0,
                        "latency_ms": latency_ms,
                        "success": False,
                        "error_type": type(exc).__name__,
                    }
                )
                logger.warning(
                    "provider_failed_falling_back",
                    provider=provider.name,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )

        raise AllProvidersFailedError(
            f"No provider could generate the script. Last error: {last_error}"
        )


async def _db_usage_recorder(payload: dict) -> None:
    """Default recorder — writes a TokenUsage row."""
    from backend.models.db import get_session_factory
    from backend.models.usage import TokenUsage

    async with get_session_factory()() as session:
        session.add(TokenUsage(**payload))
        await session.commit()


@lru_cache
def get_llm_service() -> LLMService:
    settings = get_settings()
    return LLMService(
        providers=[AzureOpenAIProvider(settings), OpenAIProvider(settings)],
        usage_recorder=_db_usage_recorder if settings.llm_fallback_enabled or True else None,
    )
