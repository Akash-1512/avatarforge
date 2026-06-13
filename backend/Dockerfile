# ── Stage 1: builder ─────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────
FROM python:3.11-slim

# Non-root user — containers should never run as root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* && groupadd -r forge && useradd -r -g forge forge

WORKDIR /app
COPY --from=builder /install /usr/local
COPY . /app/backend

RUN mkdir -p /data/media /data/eval && chown -R forge:forge /data /app
USER forge

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
