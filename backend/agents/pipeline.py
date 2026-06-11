"""Pipeline assembly and execution.

Graph: START -> script -> tts -> avatar -> store -> notify -> END
Per-node RetryPolicy covers transient faults beyond the providers' own
retries; terminal failures are handled centrally — job marked failed and
pushed to the Redis dead-letter queue for inspection/replay.
"""

import json
import time
from datetime import datetime, timezone
from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from backend.agents.nodes import PipelineNodes
from backend.agents.state import VideoPipelineState
from backend.config import get_settings
from backend.observability import tracking
from backend.observability.logging import get_logger
from backend.services.avatar.client import AvatarEngineError
from backend.services.tts.base import AllTTSProvidersFailedError

logger = get_logger(__name__)

DLQ_KEY = "avatarforge:jobs:dlq"

# Explicitly transient at the node level: full provider outages and engine
# connectivity faults. Logic errors (ValueError etc.) must NOT be retried.
_TRANSIENT = (AllTTSProvidersFailedError, AvatarEngineError, ConnectionError, TimeoutError)
_node_retry = RetryPolicy(max_attempts=2, initial_interval=0.2, retry_on=_TRANSIENT)


def build_graph(nodes: PipelineNodes):
    g = StateGraph(VideoPipelineState)
    g.add_node("script", nodes.script_node)
    g.add_node("tts", nodes.tts_node, retry_policy=_node_retry)
    g.add_node("avatar", nodes.avatar_node, retry_policy=_node_retry)
    g.add_node("store", nodes.store_node)
    g.add_node("notify", nodes.notify_node)

    g.add_edge(START, "script")
    g.add_edge("script", "tts")
    g.add_edge("tts", "avatar")
    g.add_edge("avatar", "store")
    g.add_edge("store", "notify")
    g.add_edge("notify", END)
    return g.compile()


async def push_dead_letter(job_id: str, error_type: str, error_message: str) -> None:
    """Best-effort DLQ entry in Redis."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(get_settings().redis_url)
        await client.lpush(
            DLQ_KEY,
            json.dumps(
                {
                    "job_id": job_id,
                    "error_type": error_type,
                    "error": error_message[:500],
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
        await client.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("dlq_push_failed", job_id=job_id, error=str(exc))


async def run_pipeline(job_id: str, nodes: PipelineNodes, repo) -> dict:
    """Load job, execute the graph, handle terminal failure centrally."""
    job = await repo.get(job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    state = VideoPipelineState(
        job_id=job.id,
        topic=job.topic,
        tone=job.tone,
        duration_seconds=job.duration_seconds,
        voice=job.voice,
        image_file_id=job.image_file_id,
        preprocess=job.preprocess,
    )
    graph = build_graph(nodes)
    started = time.monotonic()
    try:
        final = await graph.ainvoke(state)
        total_ms = int((time.monotonic() - started) * 1000)
        logger.info("pipeline_succeeded", job_id=job_id, total_ms=total_ms)
        tracking.log_job_run(
            job_id,
            status="completed",
            topic=job.topic,
            stage_timings=final.get("stage_timings", {}),
            llm_provider=final.get("llm_provider"),
            tts_provider=final.get("tts_provider"),
            video_duration_sec=final.get("video_duration_sec", 0.0),
        )
        return {"job_id": job_id, "status": "completed", "total_ms": total_ms}
    except Exception as exc:  # noqa: BLE001 — central terminal-failure handler
        failed_job = await repo.get(job_id)
        stage = (failed_job.current_stage if failed_job else None) or "unknown"
        await repo.fail(job_id, stage=stage, error_type=type(exc).__name__, error_message=str(exc))
        await push_dead_letter(job_id, type(exc).__name__, str(exc))
        tracking.log_job_run(
            job_id,
            status="failed",
            topic=job.topic,
            stage_timings={},
            error_type=type(exc).__name__,
        )
        logger.error(
            "pipeline_failed",
            job_id=job_id,
            stage=stage,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise


@lru_cache
def get_default_nodes() -> PipelineNodes:
    from backend.services.avatar.service import get_avatar_service
    from backend.services.jobs.repository import get_job_repository
    from backend.services.llm.service import get_llm_service
    from backend.services.storage.local import get_storage
    from backend.services.tts.service import get_tts_service

    return PipelineNodes(
        llm_service=get_llm_service(),
        tts_service=get_tts_service(),
        avatar_service=get_avatar_service(),
        storage=get_storage(),
        repo=get_job_repository(),
    )
