# avatarforge v1.0.0

First complete release of the AI backend: photo + topic in, talking-head MP4
out, fully async.

## Highlights
- 5-node LangGraph pipeline on Celery — submit returns in ~300ms, inference
  runs in the background with live SSE progress
- Multi-provider resilience: Azure OpenAI → OpenAI, Azure Speech → OpenAI TTS,
  circuit breakers per provider, transient-only retries, Redis DLQ
- SadTalker as an isolated model-server container (swappable engine contract)
- MLflow tracking (per-job parent + per-stage nested runs), optional Langfuse
- Eval harness: 5 deterministic metrics + LLM-as-Judge, thresholds enforced as
  a local prompt-regression gate (judge score on shipped prompts: 4.75/5)
- Full cost audit trail; lifetime build spend under $0.01 of LLM tokens
- Alembic migrations, per-IP rate limiting, Kubernetes manifests (kind/AKS)
- 99 tests; integration contract in docs/INTEGRATION.md

## Known limitations (by design — see README "Production readiness")
- No authentication; deploy behind a gateway
- CPU inference: ~28min per 15s video; GPU or newer engines are the upgrade path
- Media on a single RWO volume; blob storage unlocks horizontal scaling
