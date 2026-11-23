FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime
ARG COMFY_REF=72212fef660bcd7d9702fa52011d089c027a64d8
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg libgl1 libglib2.0-0 curl && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/Comfy-Org/ComfyUI.git /opt/ComfyUI && cd /opt/ComfyUI && git checkout "$COMFY_REF"
WORKDIR /opt/ComfyUI
COPY constraints.txt /opt/gpu-constraints.txt
RUN pip install --no-cache-dir -c /opt/gpu-constraints.txt -r requirements.txt huggingface-hub==0.34.4
COPY download_models.py /opt/download_models.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh
ENV PYTHONUNBUFFERED=1
EXPOSE 8188
ENTRYPOINT ["/opt/entrypoint.sh"]
