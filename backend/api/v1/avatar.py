"""Avatar video generation endpoint.

Synchronous in Phase 4 — the request blocks for the full CPU inference
(2-5 minutes). Phase 5 wraps this in Celery jobs with progress streaming;
this endpoint then becomes the internal building block.
"""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.models.schemas import AvatarResponse
from backend.services.avatar.client import AvatarEngineError
from backend.services.avatar.service import AvatarService, get_avatar_service
from backend.services.avatar.validation import ImageValidationError

router = APIRouter()


@router.get("/avatar/health")
async def avatar_health(service: AvatarService = Depends(get_avatar_service)) -> dict:
    """Model server reachability + checkpoint status."""
    try:
        return await service.client.health()
    except AvatarEngineError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/avatar/generate", response_model=AvatarResponse)
async def generate_avatar(
    image: UploadFile = File(..., description="Front-facing photo, PNG/JPEG, min 256px"),
    audio_file_id: str = Form(..., description="WAV file id from /tts/synthesize"),
    preprocess: Literal["crop", "resize", "full"] = Form("crop"),
    enhancer: bool = Form(False),
    engine: Literal["sadtalker", "hunyuan"] = Form(None),
    service: AvatarService = Depends(get_avatar_service),
) -> AvatarResponse:
    """Generate a talking-head video from a photo and synthesized audio.

    Heads-up: CPU inference takes 2-5 minutes; the request blocks until done.
    """
    image_bytes = await image.read()
    try:
        return await service.generate(
            image_bytes, audio_file_id, preprocess=preprocess, enhancer=enhancer, engine=engine
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AvatarEngineError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
