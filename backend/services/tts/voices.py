"""Voice presets — one user-facing name maps to a voice on each provider,
so fallback never changes the API contract, only the timbre."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VoicePreset:
    azure_voice: str
    openai_voice: str
    description: str


VOICE_PRESETS: dict[str, VoicePreset] = {
    "professional_female": VoicePreset(
        "en-IN-NeerjaNeural", "nova", "Clear Indian English, business tone"
    ),
    "professional_male": VoicePreset(
        "en-IN-PrabhatNeural", "onyx", "Confident Indian English, business tone"
    ),
    "casual_female": VoicePreset("en-US-JennyNeural", "shimmer", "Warm US English, conversational"),
    "casual_male": VoicePreset("en-US-GuyNeural", "echo", "Friendly US English, conversational"),
    "narrator": VoicePreset("en-US-AriaNeural", "alloy", "Neutral storytelling voice"),
}

DEFAULT_VOICE = "professional_female"
