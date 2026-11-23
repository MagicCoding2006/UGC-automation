# Production operations

## First useful batch

Replace the example product, enter real economics and approved claims, and add several reviewed hooks. Add a fictional creator description or upload a licensed reference portrait. Upload 3–10 short original product clips if available; record their source and approve them.

The product editor can draft hook structures from your supplied facts without a paid LLM. Review those drafts before saving them as approved spoken copy. The creator editor can invent an original adult fictional identity brief; it generates no image or cost until a production job actually needs the portrait.

Start with three 15-second clips. In Review queue, watch each complete video with sound, check the product and captions, and score realism, lip-sync and product fidelity. A technical pass means the file decodes and has the expected format; it does not mean a face looks real or a claim is appropriate.

Approve usable clips and export the batch. The ZIP contains `final.mp4`, `captions.srt`, `poster.jpg`, a complete generation manifest, `publishing.csv` and disclosure instructions. Demo clips are excluded unless demo export is explicitly requested. Direct downloads are previews regardless of review state.

For realistic synthetic content, apply the platform's AI-generated content setting as well as any visible label. Exported disclosure copy is preparation, not a guarantee of platform acceptance. Review current platform requirements when publishing. Posting and ad spend are not automated.

## Generation state machine

```text
queued → running → review → approved / rejected
             ├→ queued (bounded retry)
             ├→ failed
             ├→ attention (uncertain provider request)
             ├→ budget_blocked
             └→ cancelled (at a checkpoint)
```

The stages are script, voice, portrait when needed, video, editing, QA and completion. Each job keeps a complete snapshot of product/creator inputs, the model route, seed and experiment arm. Later product edits do not silently change queued jobs.

Transient errors retry with backoff up to `UGC_MAX_ATTEMPTS`. Paid stages retain provider IDs. After losing a response during submission, the job enters **Needs attention**, rather than buying another generation. Review its entry in Models & setup → Provider requests:

- **Attach request:** paste the existing provider ID from your dashboard, then resume the job.
- **Confirmed: no submitted job exists:** use only after checking the provider. This permits a new paid submission.
- **Save billed cost:** replace the estimate with the actual invoice cost.
- **Prepare a new paid attempt:** for a definitively failed provider job, archive its previous request and preserve its costs before reserving a new attempt. Then resume the job.

Resuming preserves successful cached stages. It does not force a new portrait/voice/video. To deliberately produce a new source shot, change the seed, creative input or model route in a new batch.

ComfyUI errors retain their prompt ID. A failed or lost local ComfyUI process may no longer have its history; reconcile the request after inspecting its queue and output directory. HTTP avatar workers persist their own inputs and status on disk; restarting that worker recovers interrupted jobs.

## Budget behavior

Batch caps and the daily cap apply to **estimated committed and reserved provider cost**. The default daily reset uses `America/Indiana/Indianapolis`; override `UGC_TIMEZONE` with an IANA timezone. Reservations are created in a SQLite `BEGIN IMMEDIATE` transaction, so concurrent workers cannot reserve the same remaining budget twice.

The provider can bill differently from a configured estimate. Hosted talking clips reserve `actual audio seconds × configured model rate × 1.2`; TTS/portrait have separate conservative reserves. InfiniteTalk and local Wan initially reserve an hour at the configured GPU rate. Jobs pause before the next step if its reservation would exceed a cap. Changing a batch cap does not override the daily cap.

Unknown outcomes retain their reserve. Invoice reconciliation may correctly record a cost above the original reserve. The app is not a replacement for provider-side spending limits, and it cannot stop a rental host's idle/storage charges. Budget screens do not include your ad spend until you import it.

Cached portrait or footage costs belong to the first job that generated them; later reuse is free in the ledger. Batch-to-batch cost comparisons should account for that shared-asset amortization. Use total factory cost per accepted clip when deciding whether a deployment is economical.

Cancellation prevents later stages. A submitted cloud request may keep running and remain billable; ComfyUI/HTTP avatar requests can finish while a cancellation waits for the next stage checkpoint. Provider request history and spend are retained. For immediate GPU shutdown, stop the rental at the provider and reconcile the interrupted job afterward.

## Batch experiments

- **Hook:** first selected creator and model stay fixed; hooks rotate. Seeds change between replicate blocks.
- **Creator:** hook and model stay fixed; selected creators rotate. Each creator retains its own voice.
- **Model:** first creator stays fixed. Within each matched set, model variants share hook, product, creator and seed. Seed equality does not make different architectures produce identical motion.
- **Mixed:** rotates the Cartesian combinations of hooks, creators and models; exploratory, not a one-variable causal test.

Counts not divisible by the number of arms create an incomplete last block. Choose balanced multiples for clean comparisons. A batch may contain up to 1,000 jobs. No inference is performed by batch creation itself. Similar scripts and identities reuse their cached assets. Remix edits use seeded asset ordering, source offsets and pan/zoom; a tiny source library cannot create unlimited meaningful novelty.

## Metrics import

Download the CSV template in Performance. Each row represents **one creative, platform and day**:

```csv
job_id,platform,date,impressions,views,clicks,customers,revenue,media_spend
clip_REPLACE,tiktok,2026-11-23,1000,800,20,1,32,10
```

The sample is illustrative and is not imported automatically. Use actual creative IDs from `publishing.csv`. Valid platforms: `tiktok`, `facebook`, `instagram`, `other`. Dates use `YYYY-MM-DD` in the reporting timezone you consistently choose. Costs/revenue use USD. `customers` means newly acquired customers, not total orders. Enforce `customers ≤ clicks ≤ impressions` for this click-attributed funnel. Use a separate offline analysis if your attribution includes view-through purchases.

The same `job_id,platform,date` replaces the previous daily snapshot. Reimporting the same CSV does not double-count. Import all days individually; do not mix daily rows with lifetime cumulative totals. A malformed file is rejected before any row changes. Limits: 2 MB and 10,000 rows.

## Recurring production

Create an automation in the UI, choosing a product, route, count, interval and per-batch cap. The worker checks schedules every 15 seconds. A persistent execution slot gives each occurrence an idempotent batch ID; a crash between scheduling and job creation resumes that same slot. Failed scheduling retries after ten minutes. A global backlog guard stops creating more recurring batches once 2,000 queued/running jobs exist. Existing jobs are not dropped.

Schedules run only while the control worker is running. Missed time does not generate every historical occurrence on restart. Pausing a schedule prevents new batches; existing jobs continue. Review can remain manual while generation runs unattended.

`UGC_AUTO_APPROVE=true` enables automatic approval only after **three prior human-approved clips** on the same product/creator/model configuration have realism, lip-sync and product scores all at least 4/5. Changes to the product, creator or model configuration invalidate this qualification hash. Demo outputs never auto-approve. Continue sampling output and revoke this setting when testing a new route. Caption/visual checks remain imperfect.

## CLI and API

The CLI reads the root `.env` without displaying tokens. It uses only Python's standard library:

```bash
python scripts/ugc.py doctor
python scripts/ugc.py state
```

Get product and creator IDs from `state`. Generate a spec without spending anything:

```bash
python scripts/benchmark.py --product PRODUCT_ID --creator CREATOR_ID --models fabric-480 fabric-720 --replicates 10 --budget 75 --output benchmark.json
python scripts/ugc.py generate --spec benchmark.json --key model-pilot-001
python scripts/ugc.py watch BATCH_ID
python scripts/ugc.py export BATCH_ID --output exports
```

`--key` makes retries of the same submission idempotent; use a different key for a genuinely new batch. Reusing a key with a different request is rejected. Protect exported files and the `.env` containing your keys.

The same API used by the UI is documented at `http://localhost:8000/api/docs`. For external automation send `Authorization: Bearer <UGC_TOKEN>`. No CORS access is enabled; browser UI and API use the same origin.

Core routes:

| Route | Purpose |
| --- | --- |
| `GET /api/state` | Workspace, queue, costs, models and reports |
| `POST /api/products`, `PUT /api/products/{id}` | Product knowledge |
| `POST /api/creators`, `PUT /api/creators/{id}` | Creator identity |
| `POST /api/assets` | Multipart file, rights, approval and optional product |
| `POST /api/batches/quote` | Estimate without inference |
| `POST /api/batches` | Queue a batch; optional `Idempotency-Key` |
| `GET /api/jobs?batch_id=...&status=...&limit=...&offset=...` | Paginated jobs |
| `POST /api/jobs/{id}/review` | Human review and scores |
| `POST /api/jobs/{id}/retry`, `/cancel` | Resume/cancel |
| `PATCH /api/batches/{id}/budget` | Adjust cap without changing existing costs |
| `GET /api/batches/{id}/export` | Approved production export ZIP |
| `POST /api/metrics/import` | Multipart daily metrics CSV |
| `GET /api/analytics?batch_id=...` | Product/model or experiment-arm metrics |
| `POST /api/automations` | Recurring batch configuration |
| `GET /api/requests`, `POST /api/requests/{key}/reconcile` | Provider history and costs |

## Scaling and backups

One control host keeps SQLite and local media on a normal local filesystem. GPU services may run on separate hosts. Do not mount SQLite through NFS or share its file between machines. The supported scaling path is more remote inference capacity and several CPU workers on the **same** control host. Keep the local GPU queue serial. At multi-host control-plane scale, replace the queue/database with PostgreSQL plus object storage and a distributed queue; those are not silently emulated here.

Back up the database and media together. For the clearest backup boundary, wait for active jobs to finish, stop the worker, then run:

```bash
docker compose stop worker
docker compose exec api python /app/scripts/backup.py /app/data/backups
docker compose start worker
```

Copy the resulting archive off the volume. It contains a SQLite backup snapshot and media; your root `.env` is intentionally separate. To restore onto a stopped deployment, extract the archive into the control data directory/volume, preserving `ugc.sqlite3` and `media/`, then start services. Test recovery on a separate copy before relying on backups. Model volumes can be redownloaded but are expensive; retain them separately if useful.

Generated clips and model caches accumulate. There is no automatic deletion of approved footage. Watch disk usage and archive campaigns deliberately. A 1,000-job queue tests orchestration capacity, not a claim that the GPU can finish 1,000 clips by a particular deadline.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Worker offline | `docker compose logs worker`; ensure API/worker share `studio-data` |
| Sign-in fails | Read `UGC_TOKEN` from `.env`; recreate API after changing it |
| GPU runtime unavailable | Verify `nvidia-smi`, NVIDIA Container Toolkit / WSL2 integration |
| GPU OOM | Reduce Wan resolution/frames; stop other GPU applications; keep one GPU job |
| Portrait setup fails | Set FAL_KEY or upload an approved creator reference |
| Paid request uncertain | Reconcile its existing provider ID; do not clear it blindly |
| No exported videos | Approve finished clips; demo export needs explicit demo inclusion |
| Captions drift | Review approximate timing; edit exported SRT or add a forced-alignment adapter |
| Metrics look too good | Check new-customer definitions, cumulative rows, shared-asset amortization and attribution windows |
| API 403 behind proxy | Preserve matching Host/Origin; configure TLS cookies correctly |
| Compose rejects GPU config | Update Compose; files use device reservations for broader compatibility |
