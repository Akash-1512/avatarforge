# SadTalker model server — isolated heavy-ML container.
# CPU-only PyTorch; pinned versions known to work with SadTalker's stack.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU torch first (large layer, cache it early)
RUN pip install --no-cache-dir torch==2.0.1 torchvision==0.15.2 \
    --index-url https://download.pytorch.org/whl/cpu

# SadTalker at a pinned commit for reproducibility
RUN git clone https://github.com/OpenTalker/SadTalker.git /app/SadTalker && \
    cd /app/SadTalker && git checkout cd4c0465ae0b54a6f85af57f5c65fec9fe23e7f8

# Pinned dependency set known to work with torch 2.0.1 / SadTalker
RUN pip install --no-cache-dir \
    numpy==1.23.5 face_alignment==1.3.5 imageio==2.19.3 imageio-ffmpeg==0.4.7 \
    librosa==0.9.2 numba resampy==0.3.1 pydub==0.25.1 scipy==1.10.1 \
    kornia==0.6.8 tqdm yacs==0.1.8 pyyaml joblib==1.1.0 \
    scikit-image==0.19.3 basicsr==1.4.2 facexlib==0.3.0 gfpgan==1.3.8 \
    av safetensors fastapi==0.115.6 uvicorn==0.34.0 python-multipart==0.0.20

COPY server.py download_models.py /app/

ENV SADTALKER_DIR=/app/SadTalker \
    CHECKPOINT_DIR=/models/sadtalker \
    PYTHONUNBUFFERED=1

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
