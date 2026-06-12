# Running the HunyuanVideo-Avatar engine on RunPod

The quality engine needs an NVIDIA GPU (official minimum: 24GB VRAM, "very
slow"; comfortable: A100 80GB). Rather than owning one, rent by the second
and point `HUNYUAN_URL` at the pod. The rest of avatarforge keeps running
locally on CPU — only avatar inference travels.

## Cost math (June 2026 rates)

| GPU | $/hr | fits how | realistic use |
|---|---|---|---|
| RTX 4090 24GB (community) | ~$0.34 | fp8 + `--cpu-offload`, slow | cheapest trial |
| A100 80GB | ~$1.39 | fp8, no offload | demo batch |

A demo session — boot, download nothing (weights cached on a volume after
first time), render 4–6 clips, shut down — is roughly **$1–3 on an A100**.
First-ever session adds ~30–60 min of weight download (~30GB+), so attach a
**network volume** and pay for that download exactly once.

Generation unit: `--sample-n-frames 129` ≈ **5 seconds of video** at 25fps.
Raising frames raises VRAM superlinearly. For quality-tier demos, write short
punchy scripts (the `duration_seconds=15` floor in the API is already more
than one Hunyuan clip; keep audio ≤5s for a single-clip render).

## One-time setup

1. RunPod → Pods → Deploy. Pick **A100 80GB** (or 4090 to trial). Template:
   any CUDA 12.x PyTorch image, or use Docker directly with our image.
2. Attach a **Network Volume** (60GB+) mounted at `/weights`.
3. Expose **HTTP port 8002**.

In the pod terminal:

```bash
git clone https://github.com/Akash-1512/avatarforge.git
cd avatarforge/hunyuan

# Build and start the model server (or run the steps from the Dockerfile manually
# inside RunPod's pytorch image if docker-in-docker isn't available):
docker build -t avatarforge-hunyuan .
docker run -d --gpus all -p 8002:8002 \
  -v /weights:/weights \
  -e CPU_OFFLOAD=0 \            # 1 on a 4090
  avatarforge-hunyuan

# First time only — download weights into the network volume (~30GB+):
docker exec -it $(docker ps -q -f ancestor=avatarforge-hunyuan) ./download_models.sh
```

No docker available in the pod? Run bare:

```bash
git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Avatar.git /app/HunyuanVideo-Avatar
pip install fastapi uvicorn python-multipart "huggingface_hub[cli]"
MODEL_BASE=/weights ./download_models.sh
HUNYUAN_DIR=/app/HunyuanVideo-Avatar MODEL_BASE=/weights CPU_OFFLOAD=0 \
  uvicorn server:app --host 0.0.0.0 --port 8002
```

## Connect avatarforge to it

RunPod gives the pod a proxy URL per exposed port. In your local `.env`:

```
HUNYUAN_URL=https://<pod-id>-8002.proxy.runpod.net
```

Restart the api + worker (`docker compose restart api worker`), then verify:

```powershell
Invoke-RestMethod "$env:HUNYUAN_URL/health"      # checkpoints_present: true, gpu_available: true
```

## Generate on the quality tier

```powershell
$form = @{ image = Get-Item .\face.jpg; topic = "One sentence about morning focus";
           duration_seconds = "15"; engine = "hunyuan" }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/videos/generate -Form $form
```

Same job lifecycle, same SSE stream — the job record and audit rows carry
`engine: hunyuan`, so `/metrics/summary` and MLflow distinguish the tiers.

## Shut it down

Stop the pod when done (keep the network volume). Billing stops; weights stay.
If `HUNYUAN_URL` points at a stopped pod, submitting with `engine=hunyuan`
fails fast at submit time with 503 — by design, before any money is spent.

## Honest expectations

This is the official repo's fp8 single-GPU path, the slowest-but-cheapest way
to run a model whose recommended hardware is 96GB. Expect minutes per 5-second
clip on an A100, longer with offload on a 4090. The output quality difference
vs SadTalker is dramatic — full-scene motion, natural expressions — which is
the entire point of the dual-engine architecture.
