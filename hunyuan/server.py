"""HunyuanVideo-Avatar model server — same /infer contract as the SadTalker server.

The backend can't tell the engines apart, which is the whole point: this
container accepts the identical multipart request (image + audio, plus the
SadTalker-specific fields it silently ignores) and returns an MP4.

Inference invocation mirrors the official single-GPU recipe exactly
(hymm_sp/sample_gpu_poor.py with a one-row CSV input). Tunables come from
env so a RunPod pod can be adjusted without rebuilding:

  CPU_OFFLOAD=1            enable --cpu-offload (24GB cards; slower, fits)
  SAMPLE_N_FRAMES=129      ~5s at 25fps; raising it raises VRAM needs fast
  INFER_STEPS=50           diffusion steps; lower = faster, rougher
  IMAGE_SIZE=704           generation resolution
  INFERENCE_TIMEOUT_SEC=3600
"""

import csv
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

HUNYUAN_DIR = Path(os.environ.get("HUNYUAN_DIR", "/app/HunyuanVideo-Avatar"))
MODEL_BASE = Path(os.environ.get("MODEL_BASE", "/weights"))
RESULTS_DIR = Path("/tmp/hunyuan-results")
INFERENCE_TIMEOUT_SEC = int(os.environ.get("INFERENCE_TIMEOUT_SEC", "3600"))
CPU_OFFLOAD = os.environ.get("CPU_OFFLOAD", "0") == "1"
SAMPLE_N_FRAMES = os.environ.get("SAMPLE_N_FRAMES", "129")
INFER_STEPS = os.environ.get("INFER_STEPS", "50")
IMAGE_SIZE = os.environ.get("IMAGE_SIZE", "704")

CHECKPOINT = MODEL_BASE / "ckpts/hunyuan-video-t2v-720p/transformers/mp_rank_00_model_states_fp8.pt"

app = FastAPI(title="HunyuanVideo-Avatar model server", version="0.1.0")


def _gpu_available() -> bool:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:  # noqa: BLE001
        return False


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if (CHECKPOINT.exists() and _gpu_available()) else "degraded",
        "engine": "hunyuan-video-avatar",
        "checkpoints_present": CHECKPOINT.exists(),
        "gpu_available": _gpu_available(),
        "cpu_offload": CPU_OFFLOAD,
        "sample_n_frames": SAMPLE_N_FRAMES,
    }


@app.post("/infer")
async def infer(
    image: UploadFile = File(...),
    audio: UploadFile = File(...),
    prompt: str = Form("A person speaking directly to the camera."),
    # Accepted for contract compatibility with the SadTalker server; ignored here.
    still: bool = Form(True),
    preprocess: str = Form("crop"),
    enhancer: bool = Form(False),
):
    """Run audio-driven generation. Returns the generated MP4."""
    if not CHECKPOINT.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Checkpoint missing at {CHECKPOINT}. Run ./download_models.sh",
        )
    if not _gpu_available():
        raise HTTPException(status_code=503, detail="No NVIDIA GPU visible to this container")

    job_id = uuid.uuid4().hex
    workdir = Path(tempfile.mkdtemp(prefix=f"hy-{job_id}-"))
    save_path = RESULTS_DIR / job_id
    save_path.mkdir(parents=True, exist_ok=True)

    try:
        img_path = workdir / f"face{Path(image.filename or 'img.png').suffix or '.png'}"
        aud_path = workdir / "audio.wav"
        img_path.write_bytes(await image.read())
        aud_path.write_bytes(await audio.read())

        # The official entrypoint consumes a CSV: videoid,image,audio,prompt,fps
        csv_path = workdir / "input.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["videoid", "image", "audio", "prompt", "fps"])
            writer.writerow([job_id, str(img_path), str(aud_path), prompt, 25])

        cmd = [
            "python3", "hymm_sp/sample_gpu_poor.py",
            "--input", str(csv_path),
            "--ckpt", str(CHECKPOINT),
            "--sample-n-frames", SAMPLE_N_FRAMES,
            "--seed", "128",
            "--image-size", IMAGE_SIZE,
            "--cfg-scale", "7.5",
            "--infer-steps", INFER_STEPS,
            "--use-deepcache", "1",
            "--flow-shift-eval-video", "5.0",
            "--save-path", str(save_path),
            "--use-fp8",
            "--infer-min",
        ]
        if CPU_OFFLOAD:
            cmd.append("--cpu-offload")

        env = {
            **os.environ,
            "PYTHONPATH": str(HUNYUAN_DIR),
            "MODEL_BASE": str(MODEL_BASE),
            "DISABLE_SP": "1",
            **({"CPU_OFFLOAD": "1"} if CPU_OFFLOAD else {}),
        }
        proc = subprocess.run(
            cmd, cwd=HUNYUAN_DIR, env=env, capture_output=True, text=True,
            timeout=INFERENCE_TIMEOUT_SEC,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout)[-800:]
            raise HTTPException(status_code=500, detail=f"Inference failed: {tail}")

        videos = sorted(save_path.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not videos:
            raise HTTPException(status_code=500, detail="Inference produced no video output")
        return FileResponse(videos[-1], media_type="video/mp4", filename=f"{job_id}.mp4")

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504, detail=f"Inference exceeded {INFERENCE_TIMEOUT_SEC}s timeout"
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})
