"""Pipeline nodes — each takes state, does one stage of work, returns updates.

Nodes are methods on a class with injected services so tests swap in fakes
without patching. Persistence side-effects (stage markers) go through the
injected repository; business errors propagate and are handled centrally
by the pipeline runner (plus per-node RetryPolicy for transient faults).
"""

import time

from backend.agents.state import VideoPipelineState
from backend.models.schemas import ScriptRequest, TTSRequest
from backend.observability.logging import get_logger

logger = get_logger(__name__)


class PipelineNodes:
    def __init__(self, llm_service, tts_service, avatar_service, storage, repo, notifier=None):
        self.llm = llm_service
        self.tts = tts_service
        self.avatar = avatar_service
        self.storage = storage
        self.repo = repo
        self.notifier = notifier

    async def script_node(self, state: VideoPipelineState) -> dict:
        await self.repo.set_stage(state.job_id, "script")
        started = time.monotonic()
        resp = await self.llm.generate_script(
            ScriptRequest(
                topic=state.topic,
                tone=state.tone,
                duration_seconds=state.duration_seconds,
                language=state.language,
            )
        )
        narration = " ".join(seg.text for seg in resp.segments)
        elapsed = int((time.monotonic() - started) * 1000)
        logger.info("node_script_done", job_id=state.job_id, ms=elapsed)
        return {
            "script_title": resp.title,
            "narration": narration,
            "segments_count": len(resp.segments),
            "llm_provider": resp.provider_used,
            "stage_timings": {**state.stage_timings, "script": elapsed},
        }

    async def tts_node(self, state: VideoPipelineState) -> dict:
        await self.repo.set_stage(state.job_id, "tts")
        started = time.monotonic()
        resp = await self.tts.synthesize(
            TTSRequest(text=state.narration, voice=state.voice, language=state.language)
        )
        elapsed = int((time.monotonic() - started) * 1000)
        logger.info("node_tts_done", job_id=state.job_id, ms=elapsed)
        return {
            "audio_file_id": resp.file_id,
            "audio_duration_sec": resp.audio_duration_sec,
            "tts_provider": resp.provider_used,
            "stage_timings": {**state.stage_timings, "tts": elapsed},
        }

    async def avatar_node(self, state: VideoPipelineState) -> dict:
        await self.repo.set_stage(state.job_id, "avatar")
        started = time.monotonic()
        image_path = self.storage.resolve_path(state.image_file_id)
        if image_path is None:
            raise FileNotFoundError(f"Source image {state.image_file_id} missing from storage")
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        resp = await self.avatar.generate(
            image_bytes, state.audio_file_id, preprocess=state.preprocess, engine=state.engine
        )
        elapsed = int((time.monotonic() - started) * 1000)
        logger.info("node_avatar_done", job_id=state.job_id, ms=elapsed)
        return {
            "video_file_id": resp.file_id,
            "video_url": resp.video_url,
            "video_duration_sec": resp.video_duration_sec,
            "stage_timings": {**state.stage_timings, "avatar": elapsed},
        }

    async def store_node(self, state: VideoPipelineState) -> dict:
        """Persist all outputs to the job row — the durable record of the run."""
        await self.repo.set_stage(state.job_id, "store")
        await self.repo.complete(
            state.job_id,
            script_title=state.script_title,
            script=state.narration,
            audio_file_id=state.audio_file_id,
            video_file_id=state.video_file_id,
            video_url=state.video_url,
            stage_timings=state.stage_timings,
        )
        return {}

    async def notify_node(self, state: VideoPipelineState) -> dict:
        """Completion hook — webhook when configured, structured log always."""
        logger.info(
            "job_completed",
            job_id=state.job_id,
            video_url=state.video_url,
            timings=state.stage_timings,
        )
        if self.notifier is not None:
            try:
                await self.notifier(state)
            except Exception as exc:  # noqa: BLE001 — notification is best-effort
                logger.warning("notify_failed", job_id=state.job_id, error=str(exc))
        return {}
