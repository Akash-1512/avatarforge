"""Langfuse generation tracing — fully optional.

Activates only when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set
(free cloud tier: cloud.langfuse.com). Without keys, every call is a
no-op. All failures are swallowed: tracing never affects a request.
"""

from functools import lru_cache
from typing import Optional

from backend.config import get_settings
from backend.observability.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _get_client():
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse_init_failed", error=str(exc)[:200])
        return None


def record_generation(
    *,
    name: str,
    model: str,
    provider: str,
    input_text: str,
    output_text: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    success: bool,
    error: Optional[str] = None,
) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        gen = client.start_generation(
            name=name,
            model=model,
            input=input_text[:4000],
            metadata={"provider": provider, "latency_ms": latency_ms, "success": success},
        )
        gen.update(
            output=(output_text or error or "")[:4000],
            usage_details={"input": prompt_tokens, "output": completion_tokens},
        )
        gen.end()
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse_trace_failed", error=str(exc)[:200])
