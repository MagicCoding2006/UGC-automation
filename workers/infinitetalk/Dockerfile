# Build this on the rented GPU host or in your container registry's CI.
# CUDA 12.8 / torch 2.8 also supports Blackwell GPUs; do not use old cu121 wheels.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel
ARG INFINITALK_REF=50aa0a94184315407a991ae804d9b58d6d311ba8
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg espeak-ng libsndfile1 libgl1 libglib2.0-0 build-essential && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/MeiGen-AI/InfiniteTalk.git /opt/InfiniteTalk && cd /opt/InfiniteTalk && git checkout "$INFINITALK_REF"
WORKDIR /opt/InfiniteTalk
COPY constraints.txt /opt/gpu-constraints.txt
RUN pip install --no-cache-dir -c /opt/gpu-constraints.txt packaging ninja psutil wheel && MAX_JOBS=4 pip install --no-cache-dir -c /opt/gpu-constraints.txt flash-attn==2.8.3 --no-build-isolation
RUN pip install --no-cache-dir -c /opt/gpu-constraints.txt -r requirements.txt librosa==0.10.2.post1 soundfile==0.13.1 kokoro==0.9.4 fastapi==0.115.12 uvicorn==0.34.2 python-multipart==0.0.20 huggingface-hub==0.34.4 transformers==4.51.3 diffusers==0.35.1 xfuser==0.4.3
RUN pip install --no-cache-dir -c /opt/gpu-constraints.txt runpod==1.7.13
COPY download_models.py /service/download_models.py
COPY server.py /service/server.py
COPY runpod_handler.py /service/runpod_handler.py
COPY entrypoint.sh /service/entrypoint.sh
RUN chmod +x /service/entrypoint.sh
ENV PYTHONPATH=/opt/InfiniteTalk PYTHONUNBUFFERED=1 HF_HOME=/cache/huggingface
EXPOSE 8092
ENTRYPOINT ["/service/entrypoint.sh"]
