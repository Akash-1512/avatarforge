# avatarforge

[![CI](https://github.com/Akash-1512/avatarforge/actions/workflows/ci.yml/badge.svg)](https://github.com/Akash-1512/avatarforge/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-144%20passing-5FD08A)
![Coverage](https://img.shields.io/badge/coverage-89%25-5FD08A)
![Python](https://img.shields.io/badge/python-3.11-3A322A)
![License](https://img.shields.io/badge/license-MIT-FF8A3D)

Self-hosted AI avatar video platform — the HeyGen workflow, rebuilt as a
production-grade backend. Photo + topic in, talking-head MP4 out, with the
full engineering layer real products need: async job orchestration, provider
fallback, cost auditing, observability, and an LLM evaluation harness.

**Scope, honestly stated:** this is the AI backend and platform swimlane of a
client-style build, plus an operator console that drives and observes it (auth
and billing are deliberately out of scope — see
[Production readiness](#production-readiness)). The avatar engine is
swappable by design — SadTalker runs here at zero cost; the architecture
doesn't change when you plug in a better one.

```
topic ──► LLM script ──► neural TTS ──► lip-sync inference ──► H.264 MP4
          (Azure OpenAI    (Azure Speech    (SadTalker model
           → OpenAI         → OpenAI TTS     server, isolated
           fallback)         fallback)       container)
```

## What this demonstrates

| Engineering concern | Implementation |
|---|---|
| Async orchestration | 5-node LangGraph pipeline (script → tts → avatar → store → notify) on Celery; jobs return `202` in ~300ms while ~30min of CPU inference runs in the background |
| Resilience | Per-provider circuit breakers, multi-provider fallback (LLM and TTS), node-level `RetryPolicy` with an explicit transient-only allowlist, Redis dead-letter queue, orphaned-job guard |
| Heavy-ML isolation | SadTalker runs as a dedicated model-server container behind an HTTP contract — swap engines without touching the pipeline |
| LLMOps | MLflow run per job with nested per-stage runs; optional Langfuse generation traces; eval harness with 5 deterministic metrics + LLM-as-Judge (G-Eval pattern) acting as a prompt-regression gate |
| Cost discipline | Every AI call audited to Postgres with token counts and USD estimates; `GET /metrics/summary` computes provider success/fallback rates and spend from those rows. Entire build + verification ran on **under $0.01** of LLM spend |
| Data layer | Alembic async migrations as schema source of truth; SQLAlchemy 2.0 async throughout |
| API protection | Per-IP rate limiting (5/min on generation — each request is ~30min of CPU; unthrottled, that's a denial-of-wallet bug) |
| Kubernetes | Full manifest set (probes, resource limits, ConfigMap/Secret split, migration Job), schema-validated, deployable to kind, AKS-shaped |
| Live progress | Server-Sent Events stream per job, closes on terminal status |

## Real numbers from this machine

| metric | value |
|---|---|
| Job submission latency | 310ms to `202` |
| Script generation (gpt-4.1-mini) | 1.5–6s, ~$0.0002/script |
| TTS (Azure Speech F0) | ~1.7s for 14s of speech, $0 |
| Avatar inference (CPU, 256px) | ~28min for a 15s video (~12.7 s/frame) |
| Eval harness — LLM-as-Judge | 4.75/5 overall (flow 5.0, tone 5.0, naturalness 4.67, hook 4.33) |
| Eval harness — deterministic | duration accuracy 0.996, pacing 1.0, speakability 1.0 |
| Tests | 136 passing |

The judge also surfaced real weaknesses: scripts run slightly word-light for
their claimed durations (`spoken_duration_consistency` 0.65), and one opener
scored 3/5 on hook strength. That's the point of the harness — measurable
prompt problems instead of vibes.

## Quickstart

Prereqs: Docker, an Azure OpenAI deployment, an Azure Speech resource (F0 free
tier works). Copy `.env.example` to `.env` and fill in keys.

```bash
make dev        # api, worker, flower, sadtalker, mlflow, postgres, redis
make models     # one-time ~4GB SadTalker checkpoint download
make migrate    # alembic upgrade head
```

Windows: same targets via `.\make.ps1 dev` etc.

Generate a video:

```bash
curl -X POST http://localhost:8000/api/v1/videos/generate \
  -F image=@face.jpg \
  -F topic="One reason morning walks improve focus" \
  -F duration_seconds=15
# → {"job_id": "...", "status": "queued", ...}

curl http://localhost:8000/api/v1/jobs/<job_id>            # poll
curl -N http://localhost:8000/api/v1/jobs/<job_id>/events  # or stream
```

Consoles: API docs `:8000/docs` · Flower `:5555` · MLflow `:5000` ·
SadTalker health `:8001/health`

Quality gates (run locally before merging — keys stay off GitHub by design):

```bash
make lint && make test    # always
make eval                 # when touching prompts or eval logic; exits non-zero below thresholds
```

Kubernetes: `./scripts/deploy-kind.ps1` loads images into a kind cluster,
applies `k8s/`, creates secrets from `.env`, and runs migrations.

## Build phases

- [x] Phase 1 — FastAPI + Celery + Postgres + Redis scaffold, health checks, structured logging
- [x] Phase 2 — LLM script service: Azure OpenAI → OpenAI fallback, circuit breaker, token/cost audit
- [x] Phase 3 — TTS: Azure Speech → OpenAI fallback, SSML escaping, loudness-normalized 16kHz WAV
- [x] Phase 4 — SadTalker avatar engine (model-server pattern) + FFmpeg H.264 packaging
- [x] Phase 5 — LangGraph async pipeline, RetryPolicy, DLQ, SSE progress, Alembic
- [x] Phase 6 — MLflow tracking, Langfuse traces, eval harness with regression gate
- [x] Phase 7 — Kubernetes manifests, rate limiting, Key Vault-ready secrets
- [x] Phase 8 — Integration contract, OpenAPI polish, v1.0.0

## Operator console (v1.4)

A single-page console ships with the API and serves at `/` — open
`http://localhost:8000` after `make dev`. It's a developer/operator surface for
driving and observing the system, not a consumer product; the point is to make
the orchestration *visible*.

- **Studio** — forge a video from a one-line brief (prompt-to-video, with a plan
  preview) or from the full form (tone, duration, language, voice, engine). The
  source photo and a live pipeline track sit on the right: the four stages
  (Script -> Voice -> Avatar -> Package) light up as Server-Sent Events arrive,
  ember while running, cooling to green as each completes, and the finished MP4
  plays inline.
- **Dashboard** — spend, LLM fallback rate, avatar/speech success, and a
  live-refreshing jobs table, all computed from the audit tables via
  `/metrics/summary`; the dead-letter queue surfaces only when something is stuck.
- **Library** — a gallery of every finished video, each playable inline with its
  full generated script shown on demand, plus its language, engine, voice, and
  length. The full narration is persisted on the job row (migration 0004), so a
  completed run is a durable, replayable record — not a one-shot download.
- **Architecture view** — a system-design tab in the console: the request
  lifecycle, the LangGraph pipeline, the planner agent, the three-model engine
  registry, the provider fallback chains, and the observability rail, drawn as
  an annotated diagram. It exists so a reviewer who won't open the code can still
  see how the orchestration layer fits together. Every box maps to a real service
  in this repo, and live/configured engines are highlighted from `/avatar/engines`.
- **Per-job trace** — click any job in the Dashboard to expand its pipeline as a
  waterfall: each stage (script / voice / avatar) shows the provider that served
  it, token or character counts, cost, a proportional latency bar, and a
  **fallback** badge when the primary provider failed over. This is the LLMOps
  view — a single request reconstructed end to end. It works because every audit
  row is stamped with a `job_id` correlation id, threaded through the pipeline
  via a request-scoped context var (migration 0005), then joined back per job by
  `GET /jobs/{id}/trace`.
- **Monitoring** — the deep observability surface: dependency readiness
  (`/health/deep`), per-provider breakdowns for LLM and speech (calls, success,
  latency, cost), the jobs-by-status distribution, and the script-eval
  regression gate — per-metric scores against their thresholds plus the
  LLM-as-Judge score, served from the latest `make eval` run via
  `/metrics/eval`.

It's one self-contained file (`backend/frontend/index.html`, React via CDN, no
build step) served by an explicit FastAPI route, same-origin with the API.

## Prompt-to-video agent (v1.3)

The form has six fields; most people just want to describe what they want. The
planner turns a one-line brief into a full job spec:

```
POST /videos/plan      { "brief": "explain compound interest to teenagers, upbeat, 30s in Hindi" }
-> { "topic": "...", "tone": "enthusiastic", "duration_seconds": 30,
     "language": "hi", "voice": "casual_female", "engine": "sadtalker",
     "rationale": "..." }
```

`POST /videos/from-prompt` (brief + image) plans and submits in one call,
returning the chosen plan alongside the job handle.

What keeps it production-grade rather than a demo: the LLM proposes, but the
schema disposes. Its JSON is validated against the same field constraints the
`/videos/generate` form enforces — a hallucinated voice or a 9000-second
duration fails validation and triggers one corrective retry, then degrades to
safe defaults rather than erroring. It reuses the existing LLM service, so it
inherits the Azure->OpenAI fallback and circuit breakers with no new failure
surface. `/videos/plan` returns the spec without committing, so a UI can show
the plan for review before spending a render (the HITL seam).

## Languages & voices (v1.2)

Scripts and speech aren't English-only. The script LLM already generates in the
requested language; v1.2 makes the voice match it. A user-facing role
(`professional_female`, `narrator`, ...) resolves to a *native neural voice per
language* — so a Hindi script is spoken by a Hindi voice, Marathi by Marathi,
Tamil by Tamil, with the SSML locale set correctly. English is the baseline for
every role; unmapped languages degrade to it gracefully. Azure Speech covers
140+ locales; the curated matrix leads with the India set (hi, mr, ta) plus
es/fr/de, and extends by adding rows.

`POST /videos/generate` and `/tts/synthesize` take a `language` field (ISO-639-1).
`GET /tts/voices` returns the full role -> language -> voice matrix.

**Voice cloning** ships as an opt-in TTS path: `voice="cloned"` routes to
Chatterbox (Resemble AI, MIT-licensed) via fal, speaking arbitrary text in a
voice cloned from a short reference sample (`VOICE_CLONE_REFERENCE_URL`). It's
exclusive and pay-per-use (~$0.025/1K chars) — the standard free presets never
touch it, and it never serves them. Same `BaseTTSProvider` contract, same
circuit-breaker and audit machinery as Azure and OpenAI.

## Avatar engines (v1.1: dual-engine)

The model-server contract (`/infer`: image + audio in, MP4 out) is the seam
the whole system hangs on. v1.1 proves it by running two engines behind it:

| engine | deployment | cost | output |
|---|---|---|---|
| `sadtalker` (default) | CPU, self-hosted in compose | $0 | 2023-era talking head, head-and-shoulders |
| `hunyuan` | self-hosted GPU, 24GB+ (rented works) | ~$0.34–1.39/hr | HunyuanVideo-Avatar (Tencent, MM-DiT) — full-scene motion, natural expressions |
| `fal` | managed API (fal-ai/hunyuan-avatar) | ~$1.40 / 5s clip, $0 idle | same Hunyuan model, zero infrastructure, ~8 min/clip |

Three engines, three deployment models — local CPU, self-hosted GPU, managed
API — behind **one** `/infer`-shaped contract. Pick per request
(`engine=fal` on `/videos/generate`) or set `AVATAR_DEFAULT_ENGINE`. Jobs,
audit rows, MLflow runs, and `/metrics/summary` all carry the engine, so the
tiers stay separable in every metric. Nothing in the pipeline, retries, DLQ,
or SSE changed to add engines two and three — that was the point of the
contract.

- Self-host the GPU engine on a rented pod: [`docs/HUNYUAN_RUNPOD.md`](docs/HUNYUAN_RUNPOD.md)
- The `fal` engine needs only `FAL_API_KEY` in `.env`; one real render via
  `python scripts/fal_smoke.py face.jpg audio.wav`

## Production readiness

This build draws a deliberate line. Implemented: everything above. A real
deployment would add, in rough priority order — authentication and per-user
isolation, TLS and network policies, blob/object storage for media (the RWO
volume currently caps api/worker at one node each), CI/CD with gated merges,
Azure Key Vault via CSI driver + workload identity (the env-var indirection
makes this config-only — see `docs/SECURITY.md`), alerting and SLOs on top of
the existing metrics, multi-environment promotion, and backup/DR. None of
these require re-architecting; the seams exist.

## Documentation

- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — the API contract for consuming teams, error catalogue included
- [`docs/SECURITY.md`](docs/SECURITY.md) — secrets posture and the Key Vault path

## Stack

FastAPI · LangGraph 1.x · Celery · PostgreSQL · Redis · SadTalker · HunyuanVideo-Avatar · FFmpeg ·
Azure OpenAI · Azure Speech (140+ locales) · Chatterbox voice clone · MLflow · Langfuse · SQLAlchemy 2 async · Alembic
· slowapi · Docker Compose · Kubernetes · pytest (136 tests)

## License

MIT
