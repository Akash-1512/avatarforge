"""One-time SadTalker + GFPGAN checkpoint download (~4GB total).

Run inside the container so files land in the shared models volume:
    docker compose run --rm sadtalker python download_models.py
Idempotent: existing complete files are skipped.
"""

import os
import urllib.request
from pathlib import Path

CHECKPOINT_DIR = Path(os.environ.get("CHECKPOINT_DIR", "/models/sadtalker"))
GFPGAN_DIR = CHECKPOINT_DIR / "gfpgan" / "weights"

SADTALKER_BASE = "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc"
FILES = {
    CHECKPOINT_DIR / "mapping_00109-model.pth.tar": f"{SADTALKER_BASE}/mapping_00109-model.pth.tar",
    CHECKPOINT_DIR / "mapping_00229-model.pth.tar": f"{SADTALKER_BASE}/mapping_00229-model.pth.tar",
    CHECKPOINT_DIR / "SadTalker_V0.0.2_256.safetensors": f"{SADTALKER_BASE}/SadTalker_V0.0.2_256.safetensors",
    CHECKPOINT_DIR / "SadTalker_V0.0.2_512.safetensors": f"{SADTALKER_BASE}/SadTalker_V0.0.2_512.safetensors",
    GFPGAN_DIR / "GFPGANv1.4.pth":
        "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
    GFPGAN_DIR / "detection_Resnet50_Final.pth":
        "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
    GFPGAN_DIR / "parsing_parsenet.pth":
        "https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth",
    GFPGAN_DIR / "alignment_WFLW_4HG.pth":
        "https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth",
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"  skip (exists): {dest.name}")
        return
    print(f"  downloading: {dest.name}")

    def progress(blocks, block_size, total):
        done = blocks * block_size
        if total > 0 and blocks % 200 == 0:
            print(f"    {done / 1e6:.0f} / {total / 1e6:.0f} MB", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=progress)
    print(f"  done: {dest.name} ({dest.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    print(f"Downloading checkpoints to {CHECKPOINT_DIR} ...")
    for dest, url in FILES.items():
        download(url, dest)
    print("All checkpoints ready.")
