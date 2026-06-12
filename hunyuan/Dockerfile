# HunyuanVideo-Avatar model server — GPU quality engine.
# Builds on Tencent's official CUDA 12 image (the dependency stack is gnarly;
# don't rebuild what they already ship). Weights live in a mounted volume.
FROM hunyuanvideo/hunyuanvideo:cuda_12

RUN git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Avatar.git /app/HunyuanVideo-Avatar && \
    cd /app/HunyuanVideo-Avatar && git checkout main

RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0 python-multipart==0.0.20 \
    "huggingface_hub[cli]"

WORKDIR /app
COPY server.py download_models.sh /app/
RUN chmod +x /app/download_models.sh

ENV HUNYUAN_DIR=/app/HunyuanVideo-Avatar \
    MODEL_BASE=/weights \
    PYTHONUNBUFFERED=1

EXPOSE 8002
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
