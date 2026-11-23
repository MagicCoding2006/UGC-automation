FROM node:20-bookworm-slim AS frontend
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core libsndfile1 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt
COPY apps/api/ /app/apps/api/
COPY scripts/ /app/scripts/
COPY --from=frontend /web/dist /app/apps/web/dist
ENV PYTHONPATH=/app/apps/api UGC_DATA_DIR=/app/data PYTHONUNBUFFERED=1
RUN useradd -m -u 10001 studio && mkdir /app/data && chown studio:studio /app/data
USER studio
EXPOSE 8000
CMD ["uvicorn", "ugc.main:app", "--host", "0.0.0.0", "--port", "8000"]
