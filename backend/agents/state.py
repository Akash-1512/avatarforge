"""LangGraph pipeline state — Pydantic model, validated at every merge."""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class VideoPipelineState(BaseModel):
    # Identity + inputs
    job_id: str
    topic: str
    tone: str = "professional"
    duration_seconds: int = 60
    voice: str = "professional_female"
    image_file_id: str
    preprocess: str = "crop"

    # Produced along the way
    script_title: Optional[str] = None
    narration: Optional[str] = None
    segments_count: int = 0
    audio_file_id: Optional[str] = None
    audio_duration_sec: float = 0.0
    video_file_id: Optional[str] = None
    video_url: Optional[str] = None
    video_duration_sec: float = 0.0

    # Telemetry
    stage_timings: Dict[str, int] = Field(default_factory=dict)
    llm_provider: Optional[str] = None
    tts_provider: Optional[str] = None
