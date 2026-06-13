"""Chatterbox voice-clone TTS provider (Resemble AI) via fal.

Fourth TTS provider behind the same BaseTTSProvider contract as Azure and
OpenAI. It produces speech in a *cloned* voice: given a short reference audio
sample (configured once as a public URL), it speaks arbitrary text in that
voice. MIT-licensed model, billed per character on fal (~$0.025/1K).

Reuses fal's queue REST flow (submit -> poll 202/200 -> download), the same
pattern proven by the avatar fal engine. Voice-clone output here is the
provider's raw audio; the TTSService still normalizes it to the SadTalker WAV
spec downstream, so the rest of the pipeline is unchanged.
"""

import asyncio
import time

import httpx

from backend.config import Settings
from backend.services.tts.base import BaseTTSProvider, SynthesisResult, TTSProviderError
from backend.services.tts.voices import DEFAULT_LANGUAGE, DEFAULT_VOICE

_FAL_QUEUE = "https://queue.fal.run"
_POLL_INTERVAL_SEC = 3.0
_TIMEOUT_SEC = 300.0


class ChatterboxProvider(BaseTTSProvider):
    name = "chatterbox_fal"

    def __init__(self, settings: Settings):
        self._key = settings.fal_api_key
        self._model = settings.fal_voice_clone_model
        self._reference_url = settings.voice_clone_reference_url

    @property
    def available(self) -> bool:
        # Needs both a fal key and a reference voice to clone.
        return bool(self._key and self._reference_url)

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Key {self._key}"}

    async def synthesize(
        self,
        text: str,
        voice_preset: str = DEFAULT_VOICE,
        speaking_rate: float = 1.0,
        language: str = DEFAULT_LANGUAGE,
    ) -> SynthesisResult:
        try:
            audio = await self._generate(text)
            return SynthesisResult(audio_bytes=audio, model="chatterbox-hd", characters=len(text))
        except Exception as exc:  # noqa: BLE001 — normalize to provider error for fallback
            raise TTSProviderError(self.name, exc) from exc

    async def _generate(self, text: str) -> bytes:
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            submit = await client.post(
                f"{_FAL_QUEUE}/{self._model}",
                headers={**self._auth, "Content-Type": "application/json"},
                json={"text": text, "audio_url": self._reference_url},
            )
            if submit.status_code not in (200, 202):
                raise RuntimeError(f"fal submit {submit.status_code}: {submit.text[:160]}")
            body = submit.json()
            status_url = body["status_url"]
            response_url = body["response_url"]

        audio_url = await self._poll(status_url, response_url, started)
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
            dl = await client.get(audio_url)
            dl.raise_for_status()
            return dl.content

    async def _poll(self, status_url: str, response_url: str, started: float) -> str:
        while True:
            if time.monotonic() - started > _TIMEOUT_SEC:
                raise RuntimeError(f"chatterbox exceeded {_TIMEOUT_SEC}s")
            async with httpx.AsyncClient(timeout=15.0) as client:
                st = await client.get(status_url, headers=self._auth)
                if st.status_code not in (200, 202):
                    raise RuntimeError(f"fal status {st.status_code}")
                if st.json().get("status") == "COMPLETED":
                    res = await client.get(response_url, headers=self._auth)
                    res.raise_for_status()
                    payload = res.json()
                    audio = payload.get("audio") or {}
                    url = audio.get("url")
                    if not url:
                        raise RuntimeError(f"no audio url: {str(payload)[:160]}")
                    return url
                if st.json().get("status") in ("FAILED", "ERROR"):
                    raise RuntimeError(f"fal failed: {str(st.json())[:160]}")
            await asyncio.sleep(_POLL_INTERVAL_SEC)
