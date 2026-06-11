"""API request/response schemas and the LLM's structured-output contract."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ScriptRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500, description="What the video is about")
    tone: Literal["professional", "casual", "enthusiastic", "formal", "friendly"] = "professional"
    duration_seconds: int = Field(60, ge=15, le=300, description="Target video length")
    language: str = Field("en", min_length=2, max_length=5)
    audience: Optional[str] = Field(None, max_length=200, description="Who this video is for")


class ScriptSegment(BaseModel):
    index: int = Field(..., ge=0)
    text: str = Field(..., min_length=1)
    est_duration_sec: float = Field(..., gt=0)


class ScriptPayload(BaseModel):
    """The exact JSON structure the LLM must return — validated, never trusted."""

    title: str
    segments: List[ScriptSegment] = Field(..., min_length=1)
    total_duration_sec: float = Field(..., gt=0)


class TokenUsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class ScriptResponse(BaseModel):
    title: str
    segments: List[ScriptSegment]
    total_duration_sec: float
    provider_used: str
    model: str
    latency_ms: int
    usage: TokenUsageInfo


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: Literal[
        "professional_female", "professional_male", "casual_female", "casual_male", "narrator"
    ] = "professional_female"
    speaking_rate: float = Field(1.0, ge=0.5, le=2.0)


class TTSResponse(BaseModel):
    audio_url: str
    file_id: str
    provider_used: str
    model: str
    voice: str
    characters: int
    audio_duration_sec: float
    latency_ms: int
    estimated_cost_usd: float
    format: str


class AvatarResponse(BaseModel):
    video_url: str
    file_id: str
    video_duration_sec: float
    width: int
    height: int
    codec: str
    latency_ms: int
    preprocess: str
    enhancer: bool
