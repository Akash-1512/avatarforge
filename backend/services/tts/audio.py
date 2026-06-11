"""Audio normalization via ffmpeg.

Whatever a provider returns, the pipeline output is always:
WAV, 16kHz, mono, EBU R128 loudness-normalized — SadTalker's input spec.
Runs ffmpeg as an async subprocess; no Python audio libs needed.
"""

import asyncio
import tempfile
import wave
from pathlib import Path


class AudioProcessingError(Exception):
    pass


async def normalize_to_sadtalker_spec(audio_bytes: bytes) -> bytes:
    """Resample/remix to 16kHz mono WAV with loudness normalization."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.wav"
        dst = Path(tmp) / "out.wav"
        src.write_bytes(audio_bytes)

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-sample_fmt",
            "s16",
            str(dst),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise AudioProcessingError(f"ffmpeg failed: {stderr.decode()[-300:]}")
        return dst.read_bytes()


def wav_duration_seconds(audio_bytes: bytes) -> float:
    """Duration of a WAV payload using only the stdlib."""
    import io

    with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
        return round(wf.getnframes() / float(wf.getframerate()), 2)
