"""TTS provider contract — mirrors the LLM provider pattern."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SynthesisResult:
    audio_bytes: bytes
    model: str
    characters: int


class TTSProviderError(Exception):
    def __init__(self, provider: str, original: Exception):
        self.provider = provider
        self.original = original
        super().__init__(f"{provider}: {type(original).__name__}: {original}")


class AllTTSProvidersFailedError(Exception):
    """Every configured TTS provider failed or was circuit-broken."""


class BaseTTSProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def synthesize(
        self, text: str, voice_preset: str, speaking_rate: float = 1.0, language: str = "en"
    ) -> SynthesisResult:
        """Return raw audio bytes (WAV) for the given text."""
