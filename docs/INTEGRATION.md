# Integration guide

This is the contract the backend exposes to consuming teams (web UI, mobile,
internal tools). Everything here is stable as of v1.0.0; breaking changes bump
the major version.

Base URL (local): `http://localhost:8000/api/v1`
Interactive spec: `http://localhost:8000/docs`

## The one flow that matters

```
POST /videos/generate  ──►  202 + job_id          (milliseconds)
GET  /jobs/{id}        ──►  poll status            (or SSE below)
GET  /jobs/{id}/events ──►  text/event-stream      (closes on terminal status)
GET  {video_url}       ──►  the MP4                 (after completion)
```

### 1. Submit a job

`POST /videos/generate` — multipart/form-data, rate-limited **5/minute per IP**.

| field | type | required | notes |
|---|---|---|---|
| `image` | file | yes | front-facing photo, PNG/JPEG, min 256px/side, max 10MB |
| `topic` | string | yes | 3–500 chars, what the avatar talks about |
| `tone` | enum | no | `professional` (default), `casual`, `enthusiastic`, `formal`, `friendly` |
| `duration_seconds` | int | no | 15–300, default 60 |
| `voice` | enum | no | `professional_female` (default), `professional_male`, `casual_female`, `casual_male`, `narrator` |
| `language` | string | no | ISO-639-1 (`en` default; `hi`, `mr`, `ta`, `es`, `fr`, `de`) |
| `voice=cloned` | enum | no | routes to Chatterbox voice clone (needs reference sample configured) |
| `preprocess` | enum | no | `crop` (default), `resize`, `full` |
| `engine` | enum | no | `sadtalker` (default), `hunyuan` (self-host GPU), or `fal` (managed API); 503 at submit if not configured |

Response `202`:

```json
{
  "job_id": "c135539270fd4b99a12c6683222fdcc5",
  "status": "queued",
  "status_url": "/api/v1/jobs/c1355392...",
  "events_url": "/api/v1/jobs/c1355392.../events"
}
```

### 2. Track progress

`GET /jobs/{job_id}` returns the full job record:

```json
{
  "job_id": "...",
  "status": "running",          // queued | running | completed | failed
  "current_stage": "avatar",    // script | tts | avatar | store | notify | null
  "script_title": "Why Walks Boost Your Focus",
  "video_url": null,            // populated on completion
  "stage_timings_ms": {"script": 3927, "tts": 1774},
  "error_type": null,
  "error_message": null
}
```

**SSE** (`GET /jobs/{job_id}/events`, `text/event-stream`): one `data:` event per
status/stage transition, deduplicated, 1s resolution. The stream closes itself
when status reaches `completed` or `failed` — treat stream close after a
terminal event as normal, not an error. Reconnect-safe: events are snapshots,
not deltas, so a reconnect just resumes from current state.

**Timing expectations (CPU inference):** script ~2–6s, tts ~1–2s, avatar
**15–30+ minutes** per video. Build the UI around this: fire-and-forget with a
jobs list, not a spinner.

### 3. Fetch the result

`video_url` is a relative path under `/api/v1/media/...`, served with correct
`Content-Type: video/mp4` and `+faststart`, so it streams in a `<video>` tag
directly. Files are content-addressed (UUID names); URLs are stable.

## Other endpoints

| endpoint | purpose |
|---|---|
| `GET /jobs?limit=&offset=` | recent jobs, newest first (max 100/page) |
| `GET /jobs-dlq` | dead-letter queue of failed jobs |
| `GET /metrics/summary` | provider success/fallback rates, latencies, spend |
| `GET /health`, `GET /health/deep` | liveness; dependency status |
| `POST /script/generate`, `POST /tts/synthesize`, `POST /avatar/generate` | building blocks the pipeline uses; available standalone |

## Error catalogue

Errors are FastAPI-standard: `{"detail": "human-readable message"}`.

| status | when | client action |
|---|---|---|
| `404` | unknown `job_id` or media file | treat as not-found, don't retry |
| `409` | — (reserved) | — |
| `422` | invalid image (type/size/dimensions), bad form values, malformed request | fix input; message says exactly what failed |
| `429` | rate limit exceeded (5/min on generate) | back off; honor `Retry-After` if present |
| `502` | avatar engine returned an error | retryable after delay |
| `503` | engine unreachable / checkpoints missing / DLQ backend down | retryable; surface "service busy" |
| `504` | inference exceeded the engine timeout | job will appear as `failed`; resubmit |

Failed jobs carry `error_type` (exception class) and `error_message` in the job
record, and an entry in `/jobs-dlq` — enough to render a useful failure state
without parsing strings.

## What the backend does NOT do (by design)

Authentication, user accounts, billing, quotas-per-user, and the web UI are
out of this service's scope — they belong to the consuming layer. The API is
unauthenticated in this build; put it behind your gateway.
