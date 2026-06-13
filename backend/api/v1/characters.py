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


@router.get("/scene/styles")
async def scene_styles() -> dict:
    from backend.services.style.service import get_style_service

    svc = get_style_service()
    return {"styles": svc.supported(), "configured": svc.configured()}


@router.post("/characters/{user_id}/{character_id}/restyle")
async def restyle_character(user_id: str, character_id: str, style: str = Form(...)) -> dict:
    """Render the character's first reference frame in a chosen style.

    Realistic is a pass-through; stylized targets run through the FLUX-LoRA style
    engine. Returns the stored stylized still id.
    """
    from backend.services.storage.local import get_storage
    from backend.services.style.service import StyleEngineError, get_style_service

    char = await get_character_service().get(character_id)
    if char is None or char.user_id != user_id:
        raise HTTPException(status_code=404, detail="Character not found")
    frames = char.frame_ids()
    if not frames:
        raise HTTPException(status_code=422, detail="Character has no reference frames")

    storage = get_storage()
    path = storage.resolve_path(frames[0])
    if not path:
        raise HTTPException(status_code=404, detail="Reference frame missing from storage")
    with open(path, "rb") as fh:
        image_bytes = fh.read()

    try:
        out = await get_style_service().restyle(image_bytes, style)
    except StyleEngineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    stored = await storage.save_bytes(out, "jpg")
    return {"character_id": character_id, "style": style, "still_id": stored.file_id}


class LipSyncRequest(BaseModel):
    still_id: str
    audio_id: str
    resolution: str = "720p"


@router.post("/scene/lipsync")
async def scene_lipsync(req: LipSyncRequest) -> dict:
    """Make a still speak: image + audio -> lip-synced talking clip (VEED Fabric)."""
    from backend.services.scene.lipsync_client import LipSyncError, get_lipsync_service
    from backend.services.storage.local import get_storage

    storage = get_storage()
    img_path = storage.resolve_path(req.still_id)
    aud_path = storage.resolve_path(req.audio_id)
    if not img_path or not aud_path:
        raise HTTPException(status_code=404, detail="still_id or audio_id not found")
    with open(img_path, "rb") as fh:
        image_bytes = fh.read()
    with open(aud_path, "rb") as fh:
        audio_bytes = fh.read()

    try:
        video = await get_lipsync_service().sync(image_bytes, audio_bytes, req.resolution)
    except LipSyncError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    stored = await storage.save_bytes(video, "mp4")
    return {"clip_id": stored.file_id, "resolution": req.resolution}


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
