"""Composition — render a Storyboard into one assembled short.

Fans out the storyboard: each scene becomes a routed scene-engine call (content
policy decides the engine, exactly as for a single preview), then the per-scene
clips are concatenated with FFmpeg into one MP4. Scene prompts are built from the
shot + camera + the chosen style so the look is consistent across cuts.

This is the multi-scene spine. Per-scene tracing and the music/caption finish ride
on top in the same place the existing trace is assembled; the self-correcting
quality loop (Phase 4) wraps the per-scene render with a critique/retry.
"""

import asyncio
import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional

from backend.observability.logging import get_logger
from backend.services.director.service import Storyboard
from backend.services.scene.service import SceneRequest, SceneService
from backend.services.scene.sora2_client import SceneEngineError

logger = get_logger(__name__)


@dataclass
class SceneClip:
    index: int
    engine: str
    seconds: int
    video: bytes


@dataclass
class CompositionResult:
    clips: List[SceneClip]
    stitched: bytes
    total_seconds: int


class CompositionError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def scene_prompt(shot: str, camera: str, style: str) -> str:
    """Compose a render prompt from a storyboard cell + the global style."""
    style_phrase = "" if style == "realistic" else f", {style} style"
    cam = f", {camera}" if camera else ""
    return f"{shot}{cam}{style_phrase}".strip()


class CompositionService:
    def __init__(self, scenes: SceneService):
        self.scenes = scenes

    async def render(
        self, board: Storyboard, has_real_face: bool = False, engine: Optional[str] = None
    ) -> CompositionResult:
        if not board.scenes:
            raise CompositionError("Storyboard has no scenes", 422)

        clips: List[SceneClip] = []
        for i, sc in enumerate(board.scenes):
            req = SceneRequest(
                prompt=scene_prompt(sc.shot, sc.camera, board.style),
                seconds=sc.seconds,
                has_real_face_reference=has_real_face,
                engine=engine,
            )
            engine_name = self.scenes.route(req)
            try:
                video = await self.scenes.generate(req)
            except SceneEngineError as exc:
                raise CompositionError(
                    f"Scene {i + 1} failed on engine '{engine_name}': {exc}", exc.status_code
                ) from exc
            clips.append(SceneClip(index=i, engine=engine_name, seconds=sc.seconds, video=video))
            logger.info("scene_rendered", index=i, engine=engine_name, seconds=sc.seconds)

        stitched = await self._stitch([c.video for c in clips])
        return CompositionResult(clips=clips, stitched=stitched, total_seconds=board.total_seconds)

    async def _stitch(self, videos: List[bytes]) -> bytes:
        """Concatenate scene MP4s into one, re-encoding for uniform timebase."""
        if len(videos) == 1:
            return videos[0]
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, v in enumerate(videos):
                p = os.path.join(tmp, f"s{i:02d}.mp4")
                with open(p, "wb") as fh:
                    fh.write(v)
                paths.append(p)
            listfile = os.path.join(tmp, "list.txt")
            with open(listfile, "w") as fh:
                for p in paths:
                    fh.write(f"file '{p}'\n")
            out = os.path.join(tmp, "out.mp4")
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                listfile,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                out,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise CompositionError(f"stitch failed: {stderr.decode()[-300:]}")
            with open(out, "rb") as fh:
                return fh.read()


def get_composition_service() -> CompositionService:
    from backend.services.scene.service import get_scene_service

    return CompositionService(get_scene_service())
