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

    async def render_with_cast(self, board: Storyboard, cast, reference_loader=None):
        """Render a storyboard where each scene names a cast role. The scene is
        routed by *that member's* content policy (a real-person role forces a
        reference-capable engine, fed the member's avatar frame) and rendered in
        that member's style; scenes with no role fall back to the board style and
        text-to-scene routing.

        `reference_loader(avatar_id) -> bytes|None` resolves a member's frame; it
        defaults to the storage-backed loader but is injectable for testing/decoupling.
        """
        if not board.scenes:
            raise CompositionError("Storyboard has no scenes", 422)
        load_ref = reference_loader or self._load_reference

        clips: List[SceneClip] = []
        for i, sc in enumerate(board.scenes):
            member = cast.member_for(sc.role) if sc.role else None
            style = member.style if member else board.style
            has_real_face = bool(member.is_real_person) if member else False
            reference = None
            if member and member.is_real_person:
                reference = await load_ref(member.avatar_id)
            req = SceneRequest(
                prompt=scene_prompt(sc.shot, sc.camera, style),
                seconds=sc.seconds,
                has_real_face_reference=has_real_face,
                reference_image=reference,
            )
            engine_name = self.scenes.route(req)
            try:
                video = await self.scenes.generate(req)
            except SceneEngineError as exc:
                raise CompositionError(
                    f"Scene {i + 1} (role '{sc.role or '-'}') failed on '{engine_name}': {exc}",
                    exc.status_code,
                ) from exc

            # voice + lip-sync: if the scene has dialogue and a member, speak it in
            # the member's voice and lip-sync onto the clip. Resilient — any failure
            # keeps the silent clip rather than failing the film.
            spoke = False
            if member and sc.dialogue:
                voiced = await self._voice_and_sync(video, sc.dialogue, member, load_ref)
                if voiced is not None:
                    video, spoke = voiced, True

            clips.append(SceneClip(index=i, engine=engine_name, seconds=sc.seconds, video=video))
            logger.info(
                "scene_rendered",
                index=i,
                engine=engine_name,
                role=sc.role or "-",
                style=style,
                voiced=spoke,
            )

        stitched = await self._stitch([c.video for c in clips])
        return CompositionResult(clips=clips, stitched=stitched, total_seconds=board.total_seconds)

    async def _voice_and_sync(self, video, dialogue, member, load_ref=None) -> Optional[bytes]:
        """Speak the dialogue in the member's voice and lip-sync it onto a frame of
        the clip. Returns the talking clip, or None on any failure (keep the silent
        clip). A real-person member uses its reference frame as the talking face;
        otherwise a frame is pulled from the rendered clip."""
        try:
            from backend.services.scene.lipsync_client import get_lipsync_service
            from backend.services.voice.service import get_voiceover_service

            audio = await get_voiceover_service().speak(dialogue, voice=member.voice)
            if not audio:
                return None
            lip = get_lipsync_service()
            if not lip.configured():
                return None
            # the talking face: the member's reference frame if available, else a
            # frame extracted from the rendered scene.
            face = None
            if member.is_real_person and load_ref:
                face = await load_ref(member.avatar_id)
            if face is None:
                face = await self._frame_from_clip(video)
            if face is None:
                return None
            return await lip.sync(face, audio, resolution="720p")
        except Exception as exc:  # noqa: BLE001 — voiceover is best-effort
            logger.warning("voice_sync_failed", role=member.role, err=str(exc)[:160])
            return None

    async def _frame_from_clip(self, video: bytes) -> Optional[bytes]:
        """Extract a single representative frame (JPEG) from a clip via FFmpeg."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "c.mp4")
            out = os.path.join(tmp, "f.jpg")
            with open(src, "wb") as fh:
                fh.write(video)
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                src,
                "-vf",
                "thumbnail",
                "-frames:v",
                "1",
                "-q:v",
                "3",
                out,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            if proc.returncode != 0 or not os.path.exists(out):
                return None
            with open(out, "rb") as fh:
                return fh.read()

    async def _load_reference(self, avatar_id: str) -> Optional[bytes]:
        """Load a character's first reference frame from storage (for Kling)."""
        from backend.services.character.service import get_character_service
        from backend.services.storage.local import get_storage

        char = await get_character_service().get(avatar_id)
        if char is None:
            return None
        frames = char.frame_ids()
        if not frames:
            return None
        path = get_storage().resolve_path(frames[0])
        if not path:
            return None
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            return None

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
