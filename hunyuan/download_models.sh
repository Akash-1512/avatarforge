#!/usr/bin/env bash
# One-time HunyuanVideo-Avatar weights download (~30GB+) into $MODEL_BASE.
# Run inside the container:  docker compose run --rm hunyuan ./download_models.sh
set -euo pipefail
MODEL_BASE="${MODEL_BASE:-/weights}"
echo "Downloading tencent/HunyuanVideo-Avatar weights to ${MODEL_BASE} ..."
huggingface-cli download tencent/HunyuanVideo-Avatar --local-dir "${MODEL_BASE}"
echo "Done. Expect: ${MODEL_BASE}/ckpts/hunyuan-video-t2v-720p/transformers/mp_rank_00_model_states_fp8.pt"
