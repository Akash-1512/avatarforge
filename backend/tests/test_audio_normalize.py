"""Audio normalization — real ffmpeg, real audio. Generates a 44.1kHz
stereo tone and verifies the output meets SadTalker's spec exactly."""

import io
import subprocess
import wave

import pytest

from backend.services.tts.audio import (
    AudioProcessingError,
    normalize_to_sadtalker_spec,
    wav_duration_seconds,
)


def _make_test_wav() -> bytes:
    """1-second 440Hz stereo tone at 44.1kHz — deliberately the WRONG spec."""
    out = subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-f",
            "wav",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return out.stdout


@pytest.mark.asyncio
async def test_normalizes_to_16khz_mono():
    raw = _make_test_wav()
    normalized = await normalize_to_sadtalker_spec(raw)
    with wave.open(io.BytesIO(normalized), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2  # s16


@pytest.mark.asyncio
async def test_duration_preserved():
    raw = _make_test_wav()
    normalized = await normalize_to_sadtalker_spec(raw)
    assert 0.8 <= wav_duration_seconds(normalized) <= 1.3


@pytest.mark.asyncio
async def test_garbage_input_raises():
    with pytest.raises(AudioProcessingError):
        await normalize_to_sadtalker_spec(b"this is not audio")
