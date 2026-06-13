"""Text-to-speech endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from backend.models.schemas import TTSRequest, TTSResponse
from backend.services.tts.base import AllTTSProvidersFailedError
from backend.services.tts.service import TTSService, get_tts_service
from backend.services.tts.voices import VOICE_MATRIX

router = APIRouter()


@router.get("/tts/voices")
async def list_voices() -> dict:
    """Available voice presets and their per-provider mapping."""
    return {
        role: {
            "languages": sorted(by_lang.keys()),
            "voices": {
                lang: {"azure_voice": p.azure_voice, "locale": p.locale, "desc": p.description}
                for lang, p in by_lang.items()
            },
        }
        for role, by_lang in VOICE_MATRIX.items()
    }


@router.post("/tts/synthesize", response_model=TTSResponse)
async def synthesize(
    request: TTSRequest,
    service: TTSService = Depends(get_tts_service),
) -> TTSResponse:
    """Synthesize speech. Azure Speech first, OpenAI TTS fallback.

    Output is always WAV 16kHz mono, loudness-normalized — ready for the
    avatar lip-sync stage.
    """
    try:
        return await service.synthesize(request)
    except AllTTSProvidersFailedError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Speech synthesis is temporarily unavailable: {exc}",
        ) from exc
