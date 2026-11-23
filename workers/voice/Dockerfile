FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng libsndfile1 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /service
RUN pip install --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
ENV HF_HOME=/models PYTHONUNBUFFERED=1
EXPOSE 8091
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8091", "--workers", "1"]
