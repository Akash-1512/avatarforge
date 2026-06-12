# avatarforge

> AI avatar video generation platform — type a topic, get a talking-head video.
> FastAPI · LangGraph · Azure OpenAI · SadTalker · Celery · Zero-budget stack.

[![CI](https://github.com/Akash-1512/avatarforge/actions/workflows/ci.yml/badge.svg)](https://github.com/Akash-1512/avatarforge/actions)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## What it does

1. **Script** — Azure OpenAI generates a time-segmented video script from your topic (OpenAI fallback)
2. **Voice** — Azure Speech synthesizes natural speech with SSML control (OpenAI TTS fallback)
3. **Avatar** — SadTalker lip-syncs your photo to the audio, FFmpeg packages the MP4
4. **Pipeline** — LangGraph orchestrates the flow, Celery runs it async, full observability via MLflow + Langfuse

## Quick start

```bash
git clone https://github.com/Akash-1512/avatarforge.git
cd avatarforge
cp .env.example .env        # add your API keys
make dev                    # starts everything
make models                 # one-time: download SadTalker checkpoints (~4GB)
```

| Service | URL |
|---|---|
| API docs | http://localhost:8000/docs |
| Flower (job dashboard) | http://localhost:5555 |
| Health check | http://localhost:8000/api/v1/health |

## Architecture

```
Topic ──► [Script Node] ──► [TTS Node] ──► [Avatar Node] ──► [Storage] ──► MP4
            Azure OpenAI      Azure Speech    SadTalker         local/blob
            ↓ fallback        ↓ fallback      + FFmpeg
            OpenAI            OpenAI TTS
```

Orchestrated by **LangGraph** state machine · executed by **Celery** workers · traced in **MLflow + Langfuse**.

## Development

```bash
make test     # pytest with coverage
make lint     # black, isort, flake8, mypy
make format   # auto-format
make smoke    # fire a Celery round-trip test
make logs     # tail all containers
```

## Project status

- [x] Phase 1 — Scaffold, Docker Compose, CI, health checks
- [x] Phase 2 — LLM service (Azure OpenAI → OpenAI fallback, circuit breaker, token audit)
- [x] Phase 3 — TTS service (Azure Speech → OpenAI TTS fallback, SSML, 16kHz mono output)
- [x] Phase 4 — SadTalker avatar engine (model-server pattern) + FFmpeg packaging
- [x] Phase 5 — LangGraph async pipeline (5 nodes, RetryPolicy, DLQ, SSE progress) + Alembic
- [x] Phase 6 — MLflow tracking, Langfuse traces, eval harness (deterministic + LLM-as-Judge) with regression gate
- [x] Phase 7 — CI/CD (lint, test, docker, k8s-validate, eval gate), K8s manifests, rate limiting, Key Vault-ready secrets
- [ ] Phase 8 — v1.0.0 release

## License

MIT © Akash Chaudhari
