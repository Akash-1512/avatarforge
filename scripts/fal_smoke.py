"""One real fal render, no stack required. Proves the engine end to end.

Usage:
    export FAL_API_KEY=...        # or set in env (Windows: $env:FAL_API_KEY=...)
    python scripts/fal_smoke.py path/to/face.jpg path/to/audio.wav

Costs ~$1.40 for a 5s clip, billed only on success. Writes fal_out.mp4.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.config import Settings  # noqa: E402
from backend.services.avatar.fal_client import FalAvatarClient  # noqa: E402


async def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    image_path, audio_path = sys.argv[1], sys.argv[2]
    ext = image_path.rsplit(".", 1)[-1].lower().replace("jpg", "jpeg")

    key = os.environ.get("FAL_API_KEY", "")
    if not key:
        print("Set FAL_API_KEY first.")
        sys.exit(1)

    client = FalAvatarClient(Settings(fal_api_key=key, avatar_inference_timeout_sec=900))
    print(f"Health: {await client.health()}")
    print("Submitting to fal (this takes ~8 min)...")

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    video = await client.infer(image_bytes, ext, audio_bytes)
    with open("fal_out.mp4", "wb") as f:
        f.write(video)
    print(f"Done: fal_out.mp4 ({len(video):,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
