"""Azure Speech (REST) primary, OpenAI TTS fallback.

Azure Speech is called via its REST endpoint rather than the SDK — no
native binaries in the Docker image, and it can emit riff-16khz-16bit-mono-pcm
directly, which is exactly the format SadTalker requires downstream.
"""

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import Settings
from backend.services.tts.base import BaseTTSProvider, SynthesisResult, TTSProviderError
from backend.services.tts.ssml import build_ssml
from backend.services.tts.voices import DEFAULT_LANGUAGE, DEFAULT_VOICE, resolve_voice


class _RetryableHTTPError(Exception):
    pass


_retry_transient = retry(
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, _RetryableHTTPError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class AzureSpeechProvider(BaseTTSProvider):
    name = "azure_speech"
    # Native 16kHz mono PCM — SadTalker's required input format, no resample needed
    OUTPUT_FORMAT = "riff-16khz-16bit-mono-pcm"

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def available(self) -> bool:
        return bool(self._settings.azure_speech_key and self._settings.azure_speech_region)

    @property
    def _endpoint(self) -> str:
        region = self._settings.azure_speech_region
        return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    @_retry_transient
    async def _call(self, ssml: str) -> bytes:
        headers = {
            "Ocp-Apim-Subscription-Key": self._settings.azure_speech_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": self.OUTPUT_FORMAT,
            "User-Agent": "avatarforge",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self._endpoint, headers=headers, content=ssml.encode("utf-8"))
        if resp.status_code in (429, 500, 502, 503):
            raise _RetryableHTTPError(f"HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.content

    async def synthesize(
        self,
        text: str,
        voice_preset: str = DEFAULT_VOICE,
        speaking_rate: float = 1.0,
        language: str = DEFAULT_LANGUAGE,
    ) -> SynthesisResult:
        preset = resolve_voice(voice_preset, language)
        ssml = build_ssml(text, preset.azure_voice, speaking_rate, locale=preset.locale)
        try:
            audio = await self._call(ssml)
            return SynthesisResult(
                audio_bytes=audio, model=preset.azure_voice, characters=len(text)
            )
        except Exception as exc:  # noqa: BLE001 — normalize all transport errors
            raise TTSProviderError(self.name, exc) from exc


class OpenAITTSProvider(BaseTTSProvider):
    name = "openai_tts"

    def __init__(self, settings: Settings, model: str = "tts-1"):
        self._settings = settings
        self._model = model

    @property
    def available(self) -> bool:
        return bool(self._settings.openai_api_key)

    async def synthesize(
        self,
        text: str,
        voice_preset: str = DEFAULT_VOICE,
        speaking_rate: float = 1.0,
        language: str = DEFAULT_LANGUAGE,
    ) -> SynthesisResult:
        from openai import AsyncOpenAI

        preset = resolve_voice(voice_preset, language)
        try:
            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            resp = await client.audio.speech.create(
                model=self._model,
                voice=preset.openai_voice,
                input=text,
                response_format="wav",
                speed=max(0.25, min(4.0, speaking_rate)),
            )
            return SynthesisResult(
                audio_bytes=resp.content, model=self._model, characters=len(text)
            )
        except Exception as exc:  # noqa: BLE001
            raise TTSProviderError(self.name, exc) from exc
