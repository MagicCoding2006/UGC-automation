# ReelForge Studio

A UGC video production system built for an RTX 5070 with **12 GB VRAM and 32 GB system RAM**, with optional rented GPU workers. Product briefs become scripts, reusable fictional creators, speech, talking video or product footage, captioned vertical exports, and structured experiments.

**Start with the free demo, then connect real inference.** Demo footage is visibly labeled and never presented as realistic generated video. No provider accounts are created and no money is spent by installation.

## Start

Install and start Docker Desktop (Windows: WSL2 backend), or Docker Engine + Compose on Linux. Copy this entire folder to the target machine, or extract the portable source ZIP from `artifacts/reelforge-source.zip` after running `python scripts/package.py`. Dependencies, runtime data and secrets are excluded from that ZIP.

```powershell
# Windows PowerShell, from this folder
.\start.ps1
```

```bash
# Linux / macOS, from this folder
./start.sh
```

Open **http://localhost:8000**. Sign in with `UGC_TOKEN` from the automatically created `.env`. Use the example product to create a free batch; review the resulting MP4s and export them.

Initial Docker builds and model downloads take longer than five minutes on many connections. Once dependencies and weights are cached, setup is editing a few variables and running one command. This repository does not include a prepublished container image or model weights.

## Enable realistic talking videos

Set these in `.env`:

```dotenv
UGC_MODE=production
FAL_KEY=your_fal_key
UGC_TTS_PROVIDER=fal
```

```bash
docker compose up -d --build api worker
```

This connects **Kokoro speech → FLUX portrait → Fabric audio-driven talking video → FFmpeg edit → QA → review → export**. Upload real product photos or clips and approve their usage rights to insert accurate product cutaways. Generate the first 3–10 videos before attempting a large batch.

For inexpensive remixes, choose **Product footage remix** with approved product assets. This generates a fresh voiceover and a seeded edit without paying for new talking footage. It does not lip-sync an existing person. Wan B-roll also has voiceover, rather than a talking face.

## What is included

| Area | Implemented behavior |
| --- | --- |
| Frontend | Dashboard, product/creator editors, uploads, batch builder, paginated videos, review, experiments, analytics, schedules, model configuration, provider reconciliation |
| Creative | Hook drafts from approved facts, original fictional creator invention, approved-copy script assembly; optional local Ollama claim selection; stable portraits and voices |
| Generation | Free CPU demo; hosted Kokoro / FLUX / Fabric; included CPU Kokoro, ComfyUI/Wan and InfiniteTalk HTTP/RunPod workers |
| Editing | Vertical H.264/AAC, product cutaways, seeded remix order/offsets/pan/zoom, burned captions, SRT, audio loudness normalization, visible AI label |
| Jobs | SQLite WAL queue, atomic claims, leases, heartbeats, retries, cancellation checkpoints, cached stages, retained provider request IDs |
| Cost control | Atomic batch/daily reservations; ambiguous paid submissions stop for reconciliation; failures retain costs; actual bills can replace estimates |
| Experiments | Hook, creator and model tests; matched model scripts/creators/seeds; mixed exploration; complete input snapshots |
| Feedback | Idempotent daily CSV metrics, CTR intervals, contribution LTV, all-in CAC, cost/approved clip, expected contribution, scenario calculator |
| Automation | Durable recurring batch slots, backlog guard, CLI + HTTP API, optional approval for qualified routes, CI tests |
| Handoff | ZIP of approved MP4s, SRTs, posters, manifests, posting captions, AI disclosure copy and UTM links |

**Important limits:** visual realism, lip-sync accuracy, packaging fidelity and claim context still need human sampling. Captions use approximate script timing rather than word-level forced alignment. The system does not scrape TikTok, impersonate real creators, publish posts, import platform data directly, operate ad accounts, or guarantee profit. The experiments support valid production comparisons; organic platform delivery is not randomized.

## Choose your deployment

| Profile | Where it runs | Best starting use |
| --- | --- | --- |
| Demo | CPU, no API key | Check the complete app and export workflow |
| Hosted hybrid | Control app on your PC, inference on fal | Fastest path to realistic talking clips |
| Local voice + hosted video | CPU Kokoro + fal Fabric | Avoid per-request hosted speech cost |
| 5070 B-roll | ComfyUI/Wan 5B, 480×832, 81 frames, CPU offload | Benchmark low-cost product motion; 720p final output is upscaled |
| Dedicated avatar GPU | Included InfiniteTalk worker; start on a 48+ GB GPU with 64+ GB RAM | Compare measured accepted-video cost against hosted services |
| Serverless avatar GPU | Included RunPod handler, 0 active / 1 maximum worker initially | Stop paying for idle GPU time, with cold-start and storage tradeoffs |

Keep `UGC_WORKER_CONCURRENCY=1` on the 5070. Large video and language models should not occupy that GPU simultaneously. The local Wan workflow uses only ComfyUI core nodes, pinned model revisions, tiled decoding and CPU VAE.

## Costs

Default hosted Fabric rates are **$0.08/generated second at 480p and $0.15/second at 720p**, as documented by the provider on 2026-11-23. A 15-second avatar segment alone is therefore approximately **$1.20 or $2.25**, before other steps, failures and provider changes. Quotes reserve a buffer and can overestimate when cached assets are reused. [Provider pricing](https://fal.ai/models/veed/fabric-1.0).

Self-hosting cost depends on actual GPU runtime, startup, idle capacity, storage, electricity and rejection rates. Those have not been measured on your 5070. The defaults are editable planning rates, not promises. Use a benchmark and reconcile invoices before scaling.

The 3:1 dashboard uses **contribution LTV**, not gross revenue: `AOV × lifetime orders × contribution margin`. All-in CAC includes media and production cost per newly acquired customer. Read [the economics guide](docs/ECONOMICS.md).

## Files and guides

```text
apps/web/                 React frontend
apps/api/ugc/             API, queue, pipeline, experiments, analytics
apps/api/tests/           Behavioral, concurrency, worker-contract and render tests
workers/voice/            CPU Kokoro service
workers/comfyui/          Pinned low-VRAM Wan 5B deployment
workers/infinitetalk/     Dedicated HTTP + RunPod Serverless avatar workers
scripts/                 Launch, CLI, benchmark, health and backup helpers
skills/                  Portable project-specific Codex / Claude skills
docs/                    Setup, operation, economics, architecture, sources
```

- [Target-PC and GPU setup](docs/DEPLOYMENT.md)
- [Production operations, API and troubleshooting](docs/OPERATIONS.md)
- [Architecture and extension contract](docs/ARCHITECTURE.md)
- [Benchmarking and unit economics](docs/ECONOMICS.md)
- [Verified behavior and remaining validation](docs/VALIDATION.md)
- [Upstream projects, licenses and source links](docs/SOURCES.md)

## Development

Python 3.11+, Node 20+, FFmpeg with libass, and espeak-ng (Linux) or `say` (macOS):

```bash
./scripts/dev.sh
```

For frontend development, run `npm run dev` in `apps/web`; Vite proxies `/api` and `/media` to port 8000. The API docs are at `/api/docs` after signing in. Tests use temporary databases and no paid inference:

```bash
.venv/bin/pytest -q
cd apps/web
npm run build
```

The project code is MIT-licensed. Third-party components keep their own licenses. No external skill instructions or upstream source code were copied into this project's runtime; the included skills are original and scoped to this application.
