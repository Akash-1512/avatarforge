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

**Two RunPod gotchas this runbook designs around:**
1. The HTTP proxy (`*.proxy.runpod.net`) runs through Cloudflare with a hard
   **100-second timeout** — our /infer blocks for minutes, so it would 524
   every time. **Expose the port as TCP**, not HTTP, and use the direct
   IP:port mapping instead.
2. Pods are themselves containers — no docker-in-docker. Deploy the pod
   **with Tencent's image** rather than building ours inside it.

Steps (web console):

1. RunPod → Pods → **Deploy**. GPU: **A100 80GB** (or RTX 4090 to trial with
   CPU offload).
2. Template → **Edit/Custom**: container image `hunyuanvideo/hunyuanvideo:cuda_12`,
   container start command `sleep infinity`.
3. **Expose TCP port 8002** (TCP, not HTTP — see gotcha #1). Container disk
   ≥20GB.
4. Optional but recommended: attach a **Network Volume** (60GB+) at `/weights`
   so the ~30GB weights download happens exactly once across sessions.
5. Deploy, then open the **Web Terminal** and run:

```bash
git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Avatar.git /app/HunyuanVideo-Avatar
git clone https://github.com/Akash-1512/avatarforge.git /app/avatarforge
cd /app/avatarforge/hunyuan
pip install -q fastapi==0.115.6 uvicorn==0.34.0 python-multipart==0.0.20 "huggingface_hub[cli]"

# First time only (~30GB into the volume):
MODEL_BASE=/weights bash download_models.sh

# Start the model server (CPU_OFFLOAD=1 on a 4090, 0 on A100):
HUNYUAN_DIR=/app/HunyuanVideo-Avatar MODEL_BASE=/weights CPU_OFFLOAD=0 \
  nohup uvicorn server:app --host 0.0.0.0 --port 8002 > /tmp/hunyuan.log 2>&1 &
sleep 5 && curl -s localhost:8002/health
```

Expect `"checkpoints_present": true, "gpu_available": true`.

## Connect avatarforge to it

Pod page → **Connect → TCP Port Mapping**: note the public IP and the external
port mapped to 8002 (random, e.g. `69.30.85.10:22112`). In your local `.env`:

```
HUNYUAN_URL=http://<pod-ip>:<mapped-port>
```

Recreate api + worker so they pick up the env change, then verify end to end:

```powershell
docker compose up -d --force-recreate api worker
Invoke-RestMethod "http://<pod-ip>:<mapped-port>/health"   # from your machine
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
