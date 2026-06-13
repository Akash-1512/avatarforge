"""Quality judge — does a rendered scene match what was asked for?

The judge extracts a representative frame from a rendered clip (FFmpeg) and asks a
vision model to score how well it matches the scene's intended description, returning
a structured verdict: a 0..1 match score, the concrete issues it sees, and a concrete
suggestion for re-rendering. This is the perception half of the self-correcting loop —
the loop itself (below, in the quality service) decides whether to re-render.

It calls Azure OpenAI's vision-capable chat completions directly (its own small
client) rather than routing through the text LLM fallback chain, because the judge
needs an image content block the text providers don't carry. Falls back to a
no-op "pass" verdict if no vision endpoint is configured, so the loop degrades to
single-shot rendering instead of breaking.
"""

import asyncio
import base64
import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import List

import httpx

from backend.config import Settings, get_settings
from backend.observability.logging import get_logger

logger = get_logger(__name__)

_JUDGE_SYSTEM = (
    "You are a strict film-quality reviewer. Given an intended scene description and "
    "a single frame from the rendered clip, judge how well the frame matches the "
    "intent. Respond with STRICT JSON only: "
    '{"score": 0.0-1.0, "issues": [string], "suggestion": string}. '
    "score is how well it matches (1.0 = perfect). issues are concrete mismatches. "
    "suggestion is one concrete prompt change to improve the next render."
)


@dataclass
class Verdict:
    score: float
    issues: List[str] = field(default_factory=list)
    suggestion: str = ""
    passed: bool = True  # set by the loop against its threshold


class JudgeError(Exception):
    pass


class QualityJudge:
    def __init__(self, settings: Settings):
        self._endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
        self._api_key = settings.azure_openai_api_key
        # reuse the chat deployment used elsewhere (gpt-4.1-mini is vision-capable)
        self._deployment = getattr(settings, "azure_openai_deployment", "") or "gpt-4.1-mini"

    def configured(self) -> bool:
        return bool(self._endpoint and self._api_key)

    async def extract_frame(self, video_bytes: bytes) -> bytes:
        """Grab a representative (midpoint) frame from a clip as JPEG bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "clip.mp4")
            out = os.path.join(tmp, "frame.jpg")
            with open(src, "wb") as fh:
                fh.write(video_bytes)
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                src,
                "-vf",
                "thumbnail",
                "-frames:v",
                "1",
                "-q:v",
                "3",
                out,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0 or not os.path.exists(out):
                raise JudgeError(f"frame extract failed: {stderr.decode()[-200:]}")
            with open(out, "rb") as fh:
                return fh.read()

    async def judge(self, video_bytes: bytes, intended: str) -> Verdict:
        """Score a rendered clip against its intended description."""
        if not self.configured():
            # no vision endpoint -> degrade to a passing verdict (single-shot render)
            return Verdict(score=1.0, issues=[], suggestion="", passed=True)

        frame = await self.extract_frame(video_bytes)
        data_uri = f"data:image/jpeg;base64,{base64.b64encode(frame).decode()}"
        url = (
            f"{self._endpoint}/openai/deployments/{self._deployment}"
            f"/chat/completions?api-version=2024-10-21"
        )
        payload = {
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Intended scene: {intended}"},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 400,
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                url,
                headers={"api-key": self._api_key, "Content-Type": "application/json"},
                json=payload,
            )
        if resp.status_code >= 400:
            raise JudgeError(f"judge call failed: {resp.status_code} {resp.text[:160]}")
        content = resp.json()["choices"][0]["message"]["content"]
        return self._parse(content)

    @staticmethod
    def _parse(content: str) -> Verdict:
        try:
            data = json.loads(content)
            return Verdict(
                score=float(data.get("score", 0.0)),
                issues=[str(i) for i in data.get("issues", [])][:5],
                suggestion=str(data.get("suggestion", "")).strip()[:300],
            )
        except (ValueError, TypeError, KeyError):
            # unparseable verdict -> treat as a soft pass so the loop doesn't wedge
            return Verdict(score=1.0, issues=[], suggestion="", passed=True)


def get_quality_judge() -> QualityJudge:
    return QualityJudge(get_settings())
