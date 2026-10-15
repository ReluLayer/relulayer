FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --upgrade pip

RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

RUN python3 -m pip install --no-cache-dir \
    requests \
    fastapi \
    uvicorn \
    python-multipart \
    pandas \
    openpyxl \
    transformers \
    diffusers \
    accelerate \
    bitsandbytes \
    python-pptx \
    pillow

WORKDIR /app

COPY server.py tools_data.py /app/

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
