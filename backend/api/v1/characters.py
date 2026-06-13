"""Characters + scene API.

- POST   /characters                 — ingest a photo/video/live capture into a
                                        reusable character asset.
- GET    /characters/{user_id}       — list a user's characters.
- DELETE /characters/{user_id}/{id}  — delete one.
- GET    /scene/engines              — which scene engines are configured + routing.
- POST   /scene/preview              — generate one scene clip (text-to-scene now;
                                        character-conditioned shots arrive in Phase 3).

Identity is a client-supplied user_id (no auth yet); real identity slots in here.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.services.character.ingest import IngestError
from backend.services.character.service import get_character_service
from backend.services.scene.service import SceneRequest, get_scene_service
from backend.services.scene.sora2_client import SceneEngineError

router = APIRouter()


def _char_payload(c) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "source_kind": c.source_kind,
        "default_style": c.default_style,
        "is_real_person": c.is_real_person,
        "frame_count": c.frame_count,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/characters", status_code=201)
async def create_character(
    user_id: str = Form(...),
    name: str = Form(...),
    source: UploadFile = File(...),
    source_kind: str = Form("photo"),
    default_style: str = Form("realistic"),
    is_real_person: bool = Form(True),
) -> dict:
    data = await source.read()
    try:
        char = await get_character_service().create(
            user_id=user_id,
            name=name,
            source_bytes=data,
            source_kind=source_kind,
            default_style=default_style,
            is_real_person=is_real_person,
        )
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _char_payload(char)


@router.get("/characters/{user_id}")
async def list_characters(user_id: str) -> dict:
    chars = await get_character_service().list_for_user(user_id)
    return {"user_id": user_id, "characters": [_char_payload(c) for c in chars]}


@router.delete("/characters/{user_id}/{character_id}")
async def delete_character(user_id: str, character_id: str) -> dict:
    ok = await get_character_service().delete(user_id, character_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"deleted": character_id}


@router.get("/scene/engines")
async def scene_engines() -> dict:
    return get_scene_service().available()


class ScenePreviewRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    seconds: int = Field(5, ge=1, le=20)
    size: str = "1280x720"
    character_id: str | None = None
    engine: str | None = None


@router.post("/scene/preview")
async def scene_preview(req: ScenePreviewRequest) -> dict:
    """Generate one scene clip. Routes by content policy: a character marked as a
    real person forces a reference-capable engine; otherwise text-to-scene (Sora 2).
    Returns the stored clip id. Character-conditioned reference shots land in Phase 3.
    """
    has_real_face = False
    if req.character_id:
        char = await get_character_service().get(req.character_id)
        if char is None:
            raise HTTPException(status_code=404, detail="Character not found")
        has_real_face = bool(char.is_real_person)

    scene = SceneRequest(
        prompt=req.prompt,
        seconds=req.seconds,
        size=req.size,
        has_real_face_reference=has_real_face,
        engine=req.engine,
    )
    try:
        engine_name = get_scene_service().route(scene)
        video = await get_scene_service().generate(scene)
    except SceneEngineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    from backend.services.storage.local import get_storage

    stored = await get_storage().save_bytes(video, "mp4")
    return {"engine": engine_name, "clip_id": stored.file_id, "seconds": req.seconds}
