"""Script generation endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from backend.models.schemas import ScriptRequest, ScriptResponse
from backend.services.llm.base import AllProvidersFailedError
from backend.services.llm.service import LLMService, get_llm_service

router = APIRouter()


@router.post("/script/generate", response_model=ScriptResponse, status_code=200)
async def generate_script(
    request: ScriptRequest,
    service: LLMService = Depends(get_llm_service),
) -> ScriptResponse:
    """Generate a time-segmented video script for the given topic.

    Tries Azure OpenAI first, falls back to OpenAI. Returns 503 only when
    every configured provider has failed or is circuit-broken.
    """
    try:
        return await service.generate_script(request)
    except AllProvidersFailedError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Script generation is temporarily unavailable: all LLM providers "
                f"failed or are unconfigured. ({exc})"
            ),
        ) from exc
