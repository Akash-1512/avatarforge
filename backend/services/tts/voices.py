"""Voice presets — a user-facing role (professional_female, narrator, ...)
resolves to a concrete neural voice *for a given language*.

This keeps the API contract stable across both fallback (Azure -> OpenAI,
which only changes timbre) and language (the same role speaks Hindi, Marathi,
Tamil, or English with a native voice). Azure Speech covers 140+ locales;
we curate a useful subset and fall back to English for anything unmapped.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VoicePreset:
    azure_voice: str
    openai_voice: str  # OpenAI TTS has no per-locale voices; timbre only
    locale: str
    description: str


# role -> language -> preset.  Language keys are ISO-639-1 (2-letter) to match
# ScriptRequest.language. English ("en") is the required baseline for every role.
VOICE_MATRIX: dict[str, dict[str, VoicePreset]] = {
    "professional_female": {
        "en": VoicePreset("en-IN-NeerjaNeural", "nova", "en-IN", "Indian English, business"),
        "hi": VoicePreset("hi-IN-SwaraNeural", "nova", "hi-IN", "Hindi, professional"),
        "mr": VoicePreset("mr-IN-AarohiNeural", "nova", "mr-IN", "Marathi, professional"),
        "ta": VoicePreset("ta-IN-PallaviNeural", "nova", "ta-IN", "Tamil, professional"),
        "es": VoicePreset("es-ES-ElviraNeural", "nova", "es-ES", "Spanish, professional"),
        "fr": VoicePreset("fr-FR-DeniseNeural", "nova", "fr-FR", "French, professional"),
        "de": VoicePreset("de-DE-KatjaNeural", "nova", "de-DE", "German, professional"),
    },
    "professional_male": {
        "en": VoicePreset("en-IN-PrabhatNeural", "onyx", "en-IN", "Indian English, business"),
        "hi": VoicePreset("hi-IN-MadhurNeural", "onyx", "hi-IN", "Hindi, professional"),
        "mr": VoicePreset("mr-IN-ManoharNeural", "onyx", "mr-IN", "Marathi, professional"),
        "ta": VoicePreset("ta-IN-ValluvarNeural", "onyx", "ta-IN", "Tamil, professional"),
        "es": VoicePreset("es-ES-AlvaroNeural", "onyx", "es-ES", "Spanish, professional"),
        "fr": VoicePreset("fr-FR-HenriNeural", "onyx", "fr-FR", "French, professional"),
        "de": VoicePreset("de-DE-ConradNeural", "onyx", "de-DE", "German, professional"),
    },
    "casual_female": {
        "en": VoicePreset("en-US-JennyNeural", "shimmer", "en-US", "US English, warm"),
        "hi": VoicePreset("hi-IN-SwaraNeural", "shimmer", "hi-IN", "Hindi, warm"),
    },
    "casual_male": {
        "en": VoicePreset("en-US-GuyNeural", "echo", "en-US", "US English, friendly"),
        "hi": VoicePreset("hi-IN-MadhurNeural", "echo", "hi-IN", "Hindi, friendly"),
    },
    "narrator": {
        "en": VoicePreset("en-US-AriaNeural", "alloy", "en-US", "Neutral storytelling"),
        "hi": VoicePreset("hi-IN-SwaraNeural", "alloy", "hi-IN", "Hindi narration"),
    },
}

DEFAULT_VOICE = "professional_female"
DEFAULT_LANGUAGE = "en"


def resolve_voice(role: str, language: str = DEFAULT_LANGUAGE) -> VoicePreset:
    """Pick the voice for a role+language, degrading gracefully:
    unknown role -> default role; unknown language for a role -> that role's
    English voice (always present)."""
    by_lang = VOICE_MATRIX.get(role) or VOICE_MATRIX[DEFAULT_VOICE]
    return by_lang.get(language) or by_lang[DEFAULT_LANGUAGE]


def supported_languages(role: str = DEFAULT_VOICE) -> list[str]:
    return sorted((VOICE_MATRIX.get(role) or VOICE_MATRIX[DEFAULT_VOICE]).keys())
