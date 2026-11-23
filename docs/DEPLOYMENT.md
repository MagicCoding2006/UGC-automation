# Deployment

## Fastest working production configuration

1. Copy the repository to the PC, install/start Docker Desktop with WSL2 or Docker Engine, and run `start.ps1` or `start.sh`.
2. In the root `.env`, set `UGC_MODE=production` and your `FAL_KEY`. Keep `UGC_WORKER_CONCURRENCY=1`.
3. Run `docker compose up -d --build api worker`. Open `http://localhost:8000`; use `UGC_TOKEN` from `.env` to sign in.
4. Replace the example product. Enter verified claims, audience, price, contribution margin, hooks and CTA. Add your own product footage in Asset library and approve its rights.
5. Start three 15-second Fabric 480p clips. Watch the review queue and inspect results before increasing volume.

This path needs no CUDA installation on the control PC. API keys stay in the backend. Installation never purchases credits or creates cloud infrastructure.

Five minutes of configuration is realistic with Docker already installed and a cached image. A clean Docker build, CUDA setup, account onboarding and tens of gigabytes of model downloads are additional time.

## CPU speech: save GPU memory

Set:

```dotenv
UGC_TTS_PROVIDER=local
UGC_VOICE_URL=http://voice:8091
```

```bash
docker compose --profile voice up -d --build api worker voice
```

Kokoro runs on CPU with four threads and a 4 GB memory limit. It shares no VRAM with video inference. First use downloads model files into the persistent voice cache. It uses bundled synthetic voices, not voice cloning. To revert, set `UGC_TTS_PROVIDER=fal` and recreate API/worker.

## RTX 5070: optional local B-roll

Prerequisites: current NVIDIA driver; Docker GPU access through NVIDIA Container Toolkit on Linux or Docker Desktop WSL2 GPU integration on Windows. Confirm before building:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi
```

The worker uses a CUDA 12.8 / PyTorch 2.8 image, since the RTX 50-series needs Blackwell-compatible wheels. The machine running the GPU container must be Linux x86_64 or Windows through WSL2; this is not a Mac GPU container.

```dotenv
UGC_COMFY_URL=http://comfyui:8188
UGC_LOCAL_HOURLY=0.10
```

```bash
docker compose --profile gpu up -d --build api worker comfyui
docker compose logs -f comfyui
```

On first start, the worker downloads the 5B diffusion checkpoint, FP8 text encoder and VAE at pinned Hugging Face revisions. Reserve **at least 40 GB free disk** for downloads/caches and model files, plus space for images/outputs. They are not bundled. Download time depends on bandwidth. Docker's image storage also needs free disk.

Defaults: 480×832 portrait, 81 frames (about 3.4 seconds at 24 fps), 20 steps, one job, `--lowvram`, `--cpu-vae`, tiled VAE decode, no custom nodes. Short motion clips are reused/looped under the voiceover and exported at the control app's configured size. Upscaling the final file does not add model detail.

The official ComfyUI guide describes 5B offloading on 8 GB VRAM; the 12 GB profile here is a conservative starting point, **not a measured 5070 memory guarantee**. Host RAM, drivers and background applications matter. If you hit an OOM:

- Close other GPU applications, keep one worker, and avoid loading Ollama on that GPU.
- In `apps/api/ugc/workflows.py`, lower `length` to 49 or lower dimensions in multiples of 32, then rebuild the control image.
- Inspect `docker compose logs comfyui` and the job's provider prompt ID. Resume only after resolving the failure; do not blindly resubmit uncertain jobs.

The ComfyUI service stays on the internal Docker network. A standalone deployment is also included in `workers/comfyui/compose.yaml`, bound only to loopback. It is an inference dependency, not a public web service.

## Dedicated cloud avatar worker

The `workers/infinitetalk/` directory is a complete container build context: pinned upstream source, model downloader, authenticated async HTTP API and one-at-a-time inference. Start with **48+ GB GPU, 64+ GB host RAM, 120+ GB free model/cache disk**. These are conservative provisioning suggestions pending benchmarks, not minimum-memory claims.

On a Linux GPU host with Docker GPU support:

```bash
cd workers/infinitetalk
# Put the same long UGC_WORKER_TOKEN as the control app into this host's environment.
docker compose up -d --build
```

The compose binding is `127.0.0.1:8092`; use a private network, an authenticated HTTPS reverse proxy, or the provider's HTTPS container port proxy. When deploying the image directly on RunPod Pods, expose container HTTP port **8092**, attach storage at `/models` and `/cache`, and set `UGC_WORKER_TOKEN`. Configure the control app:

```dotenv
UGC_AVATAR_TRANSPORT=http
UGC_AVATAR_URL=https://your-private-worker-host
UGC_WORKER_TOKEN=the_same_long_worker_token
UGC_GPU_HOURLY=your_effective_hourly_rate
```

The root `.env.example` contains a placeholder `http://avatar:8092`; there is no root-compose avatar service. Replace this URL when enabling InfiniteTalk.

For local testing of the remote service, use a private tunnel. If the controller is inside Docker, make sure the tunnel is reachable from that container; a Linux tunnel bound only to host loopback is not automatically reachable through the Docker bridge.

Jobs submit to `/jobs`, poll `/jobs/{key}` and download `/jobs/{key}/result`. Keys are persisted on the GPU host; a lost HTTP response reconnects to the same generation. Inputs are bounded to 20 MB each and audio to 45 seconds. Inference has a 3500-second timeout. One subprocess per generation releases GPU memory after completion; it reloads the model each time. Benchmark before optimizing to a warm persistent pipeline.

**This worker has not been executed with real CUDA/model weights in the build environment.** FlashAttention compilation, upstream compatibility and target-GPU peak memory must be validated on the host. Source and model revisions are pinned; some upstream Python dependencies still have transitive ranges. Freeze a known-working image digest after your first successful benchmark.

## RunPod Serverless: avoid idle GPU rental

The same image includes `runpod_handler.py`; the control app has a native async RunPod transport with retained job IDs.

1. Build/push the image from `workers/infinitetalk/` to your container registry. Prefer a Linux build host with enough RAM for FlashAttention compilation.
2. Create a queue-based GPU Serverless endpoint using that image. Set `AVATAR_SERVERLESS=true`, `RUNPOD_VOLUME_PATH=/runpod-volume`, **active workers=0**, **maximum workers=1**, GPU memory at least 48 GB initially, and a job execution timeout of at least 3500 seconds. Set an appropriate provider spending limit too.
3. Attach a persistent network volume with at least 120 GB free capacity. The entrypoint maps `/models` and `/cache` into it. Prewarm/download weights once. Cold starts can be expensive if every worker redownloads all weights.
4. Set the controller:

```dotenv
UGC_AVATAR_TRANSPORT=runpod
RUNPOD_API_KEY=your_runpod_key
RUNPOD_ENDPOINT_ID=your_endpoint_id
UGC_GPU_HOURLY=your_actual_serverless_hourly_equivalent
UGC_TTS_PROVIDER=local
```

5. Upload an approved creator reference or retain a `FAL_KEY` for portrait creation. Choose InfiniteTalk in the batch builder. Run one clip before a benchmark batch.

The handler returns inline base64 video, suitable for the short 15–30-second ads in this app. A high-volume or longer-video deployment should return presigned object-storage URLs instead; the default worker does not configure an S3 account. Serverless result retention is finite. Resume interrupted downloads promptly; an expired result needs manual reconciliation, not an automatic new paid submission.

Execution-time estimates exclude some model startup, idle and volume costs. Reconcile actual billed totals. Scale-to-zero avoids idle GPU rental after shutdown, but does not eliminate cold-start or storage charges. [Official worker overview](https://docs.runpod.io/serverless/workers/overview).

## Ollama script selection

The cheapest predictable default assembles approved copy without an LLM. For locally selected claim ordering:

```bash
ollama pull qwen2.5:3b
```

```dotenv
UGC_SCRIPT_PROVIDER=ollama
UGC_OLLAMA_URL=http://host.docker.internal:11434
UGC_OLLAMA_MODEL=qwen2.5:3b
```

Ollama only returns indices into the approved claims; it cannot introduce arbitrary generated product promises. Ensure Ollama is reachable from the worker container. Use CPU mode or run it on another host when local video needs the 5070.

## Remote access and persistence

Default control-app ports bind to `127.0.0.1`. For remote access, use a VPN or HTTPS reverse proxy, a random `UGC_TOKEN`, and `UGC_SECURE_COOKIE=true` behind HTTPS. Preserve the request Host and Origin consistently. This is a single-workspace app with a shared token, not a multi-tenant public SaaS.

Named volumes store the database and media. `docker compose down` preserves them; **`down -v` deletes them**. Follow the backup procedure in [OPERATIONS.md](OPERATIONS.md) before migrating. GPU model volumes and control-app data volumes are distinct.
