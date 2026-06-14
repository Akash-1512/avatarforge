"""Film API — director (brief -> storyboard) and composition (storyboard -> short).

Two steps, deliberately separate so a storyboard can be inspected/edited before
the (paid) render fans out:
- POST /director/storyboard  -> the structured plan, no rendering.
- POST /film/compose         -> render each scene + stitch into one short.

A character_id routes scene generation by content policy (real person -> a
reference-capable engine; otherwise Sora 2), the same rule used for a single scene.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.v1.auth import get_current_user
from backend.models.user import User
from backend.services.cast.service import CastError, get_cast_service
from backend.services.composition.service import CompositionError, get_composition_service
from backend.services.director.service import DirectorError, Scene, Storyboard, get_director_service

router = APIRouter()


class SceneModel(BaseModel):
    shot: str
    camera: str = ""
    dialogue: str = ""
    seconds: int = Field(5, ge=2, le=10)


class StoryboardModel(BaseModel):
    title: str
    style: str
    scenes: List[SceneModel]

    @classmethod
    def from_board(cls, b: Storyboard) -> "StoryboardModel":
        return cls(
            title=b.title,
            style=b.style,
            scenes=[
                SceneModel(shot=s.shot, camera=s.camera, dialogue=s.dialogue, seconds=s.seconds)
                for s in b.scenes
            ],
        )

    def to_board(self) -> Storyboard:
        return Storyboard(
            title=self.title,
            style=self.style,
            scenes=[
                Scene(shot=s.shot, camera=s.camera, dialogue=s.dialogue, seconds=s.seconds)
                for s in self.scenes
            ],
        )


class StoryboardRequest(BaseModel):
    brief: str = Field(..., min_length=3, max_length=2000)
    style: Optional[str] = None


@router.post("/director/storyboard")
async def make_storyboard(req: StoryboardRequest) -> dict:
    try:
        board = await get_director_service().storyboard(req.brief, req.style)
    except DirectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "storyboard": StoryboardModel.from_board(board).model_dump(),
        "scene_count": len(board.scenes),
        "total_seconds": board.total_seconds,
    }


class RefineRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    seconds: int = Field(4, ge=1, le=20)
    character_id: Optional[str] = None
    engine: Optional[str] = None
    threshold: float = Field(0.75, ge=0.0, le=1.0)
    max_iterations: int = Field(3, ge=1, le=5)


@router.post("/scene/refine")
async def refine_scene(req: RefineRequest) -> dict:
    """Render a scene with the self-correcting quality loop: render -> judge ->
    re-render with feedback until it matches the brief or hits the caps. Returns
    the best clip plus the full iteration history (scores, issues, est. spend).
    """
    from backend.services.quality.loop import get_quality_loop
    from backend.services.scene.sora2_client import SceneEngineError
    from backend.services.storage.local import get_storage

    has_real_face = False
    if req.character_id:
        from backend.services.character.service import get_character_service

        char = await get_character_service().get(req.character_id)
        if char is None:
            raise HTTPException(status_code=404, detail="Character not found")
        has_real_face = bool(char.is_real_person)

    loop = get_quality_loop()
    loop.threshold = req.threshold
    loop.max_iterations = req.max_iterations
    try:
        result = await loop.run(
            req.prompt, seconds=req.seconds, has_real_face=has_real_face, engine=req.engine
        )
    except SceneEngineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    stored = await get_storage().save_bytes(result.clip, "mp4")
    return {
        "clip_id": stored.file_id,
        "passed": result.passed,
        "best_score": result.best_score,
        "iterations": result.iterations,
        "est_cost_usd": result.est_cost_usd,
        "attempts": [
            {
                "iteration": a.iteration,
                "engine": a.engine,
                "score": round(a.score, 3),
                "issues": a.issues,
                "est_cost_usd": a.est_cost_usd,
            }
            for a in result.attempts
        ],
    }


class CastMemberModel(BaseModel):
    role: str = Field(..., min_length=1, max_length=60)
    avatar_id: str
    voice: str = ""


class CastComposeRequest(BaseModel):
    script: str = Field(..., min_length=3, max_length=8000)
    cast: List[CastMemberModel] = Field(..., min_length=1)
    theme: Optional[str] = None  # overrides per-avatar style for the whole film


@router.post("/film/cast-compose")
async def cast_compose(
    req: CastComposeRequest, current_user: User = Depends(get_current_user)
) -> dict:
    """The product's core flow: a script + a cast of named people (each bound to an
    owned avatar and a voice) -> a cast-aware storyboard -> per-member routed render
    -> one assembled short. Each role renders in its avatar's look, and a real-person
    role is forced onto a reference-capable engine."""
    try:
        cast = await get_cast_service().bind(current_user.id, [m.model_dump() for m in req.cast])
    except CastError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    roles = [m.role for m in cast.members]
    try:
        board = await get_director_service().storyboard_with_cast(
            req.script, roles, style=req.theme
        )
        result = await get_composition_service().render_with_cast(board, cast)
    except DirectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except CompositionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    from backend.services.storage.local import get_storage

    stored = await get_storage().save_bytes(result.stitched, "mp4")
    return {
        "clip_id": stored.file_id,
        "title": board.title,
        "theme": board.style,
        "cast": [
            {"role": m.role, "avatar": m.display_name, "style": m.style} for m in cast.members
        ],
        "scene_count": len(result.clips),
        "total_seconds": result.total_seconds,
        "scenes": [
            {
                "index": c.index,
                "engine": c.engine,
                "role": board.scenes[c.index].role,
                "seconds": c.seconds,
            }
            for c in result.clips
        ],
    }


class ComposeRequest(BaseModel):
    storyboard: StoryboardModel
    character_id: Optional[str] = None
    engine: Optional[str] = None


@router.post("/film/compose")
async def compose_film(req: ComposeRequest) -> dict:
    """Render every scene and stitch into one short. Returns the stored clip id."""
    has_real_face = False
    if req.character_id:
        from backend.services.character.service import get_character_service

        char = await get_character_service().get(req.character_id)
        if char is None:
            raise HTTPException(status_code=404, detail="Character not found")
        has_real_face = bool(char.is_real_person)

    board = req.storyboard.to_board()
    try:
        result = await get_composition_service().render(
            board, has_real_face=has_real_face, engine=req.engine
        )
    except CompositionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    from backend.services.storage.local import get_storage

    stored = await get_storage().save_bytes(result.stitched, "mp4")
    return {
        "clip_id": stored.file_id,
        "scene_count": len(result.clips),
        "total_seconds": result.total_seconds,
        "scenes": [
            {"index": c.index, "engine": c.engine, "seconds": c.seconds} for c in result.clips
        ],
    }
