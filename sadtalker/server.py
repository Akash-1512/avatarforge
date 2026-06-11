"""SadTalker model server — thin HTTP wrapper around inference.py.

Deliberately minimal: receive image + audio, run inference as a
subprocess, stream back the MP4. All orchestration, storage, retries,
and auditing live in the main backend; this container only does ML.
"""

import os
import shutil
import subprocess
import time
from collections import deque
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

SADTALKER_DIR = Path(os.environ.get("SADTALKER_DIR", "/app/SadTalker"))
CHECKPOINT_DIR = Path(os.environ.get("CHECKPOINT_DIR", "/models/sadtalker"))
RESULTS_DIR = Path("/tmp/sadtalker-results")
INFERENCE_TIMEOUT_SEC = int(os.environ.get("INFERENCE_TIMEOUT_SEC", "900"))

app = FastAPI(title="SadTalker model server", version="0.1.0")


def _checkpoints_present() -> bool:
    required = ["SadTalker_V0.0.2_256.safetensors", "mapping_00229-model.pth.tar"]
    return all((CHECKPOINT_DIR / f).exists() for f in required)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if _checkpoints_present() else "degraded",
        "checkpoints_present": _checkpoints_present(),
        "checkpoint_dir": str(CHECKPOINT_DIR),
    }


@app.post("/infer")
async def infer(
    image: UploadFile = File(...),
    audio: UploadFile = File(...),
    still: bool = Form(True),
    preprocess: str = Form("crop"),
    enhancer: bool = Form(False),
):
    """Run lip-sync inference. Returns the generated MP4."""
    if not _checkpoints_present():
        raise HTTPException(
            status_code=503,
            detail="Model checkpoints missing. Run: docker compose run --rm sadtalker "
            "python download_models.py",
        )
    if preprocess not in ("crop", "resize", "full"):
        raise HTTPException(status_code=422, detail="preprocess must be crop|resize|full")

    job_id = uuid.uuid4().hex
    workdir = Path(tempfile.mkdtemp(prefix=f"st-{job_id}-"))
    result_dir = RESULTS_DIR / job_id
    result_dir.mkdir(parents=True, exist_ok=True)

    try:
        img_path = workdir / f"face{Path(image.filename or 'img.png').suffix or '.png'}"
        aud_path = workdir / "audio.wav"
        img_path.write_bytes(await image.read())
        aud_path.write_bytes(await audio.read())

        cmd = [
            "python", "inference.py",
            "--driven_audio", str(aud_path),
            "--source_image", str(img_path),
            "--result_dir", str(result_dir),
            "--checkpoint_dir", str(CHECKPOINT_DIR),
            "--preprocess", preprocess,
            "--size", "256",
            "--cpu",
        ]
        if still:
            cmd.append("--still")
        if enhancer:
            cmd += ["--enhancer", "gfpgan"]

        # Stream inference output to container logs in real time so progress
        # is observable via `docker logs -f`; keep a tail for error reporting.
        proc = subprocess.Popen(
            cmd, cwd=SADTALKER_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        tail: deque[str] = deque(maxlen=80)
        started = time.monotonic()
        assert proc.stdout is not None
        for line in proc.stdout:
            print(f"[infer {job_id[:8]}] {line.rstrip()}", flush=True)
            tail.append(line)
            if time.monotonic() - started > INFERENCE_TIMEOUT_SEC:
                proc.kill()
                raise HTTPException(
                    status_code=504,
                    detail=f"Inference exceeded {INFERENCE_TIMEOUT_SEC}s timeout",
                )
        proc.wait()
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500, detail=f"Inference failed: {''.join(tail)[-600:]}"
            )

        videos = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not videos:
            raise HTTPException(status_code=500, detail="Inference produced no video output")

        return FileResponse(videos[-1], media_type="video/mp4", filename=f"{job_id}.mp4")

    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        # result_dir is cleaned lazily; FileResponse needs the file to exist after return


@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})
