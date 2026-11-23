# Validation and practical limits

The source includes an executable test suite and CI workflow. Latest complete local run: **22 passed**. Tests do not call paid inference APIs or download GPU checkpoints.

## Verified locally

- Frontend dependency installation and production Vite build.
- Python module compilation and API HTTP health/static frontend response.
- Product/creator persistence and immutable job snapshots.
- Matched script/creator/seed assignment for model experiments.
- Exclusive job claims under concurrency and expired-lease recovery.
- Concurrent budget reservations cannot oversubscribe a batch cap.
- Stable idempotency keys and actual-file cache lookup.
- Demo mode blocks paid generation routes.
- Ambiguous paid submissions stop without a new POST or cost reservation.
- Token authentication guards API and media, with same-origin mutation protection.
- Transactional metrics validation and replacement of daily snapshots without double counting.
- Correct CTR, CAC and contribution-LTV calculations.
- Blocked wording prevents a script from advancing.
- Voice worker authentication and cache contract without loading a model.
- Async avatar worker authentication, persistent keys, duplicate submission handling and result readiness.
- Complete free demo: system speech → actual FFmpeg vertical H.264/AAC MP4 → burned captions/SRT → full-decode QA → recorded human review → downloadable ZIP with manifest/CSV.
- A separate 720×1280 demo render, with audio, subtitles and a visually inspected poster. This is a labeled workflow preview, not an AI-avatar quality sample.
- Original hook drafts from supplied facts and fictional creator briefs without a paid provider.
- Compose configuration validation, including compatibility with device reservations rather than newer `gpus` shorthand.

Run `pytest -q` to see the current count and results. Integration tests use FFmpeg and espeak-ng or macOS `say`; the CI image installs those tools. The initial test run exposed and fixed an import-column mismatch and a strict FFmpeg timestamp parsing issue.

## Not verified in this environment

- Visual/interactive browser QA: the available browser runtime reported no connected browser. HTTP responses and frontend compilation passed, but that does not prove every screen is visually correct at every viewport.
- Docker image builds: Compose validates, but the local Docker daemon was not running. The app and worker were tested through a local Python environment instead.
- CUDA execution, checkpoint downloads, peak VRAM/RAM, inference time or generated-video quality on a 5070 or rented GPU.
- Live fal/RunPod paid jobs, output realism/lip-sync, provider account permissions, or actual invoices. These need your credentials and a controlled pilot.
- Real Facebook/TikTok publication, platform acceptance, attribution, or profitable acquisition. No account publishing integration is present.

The deployment folders are implemented build contexts and adapters, rather than executed cloud deployments. Expect an initial hardware/provider smoke test and possible dependency adjustment in the GPU images. Save the successful image digest and measured model settings when that test passes.

## A minimal hardware acceptance check

1. One hosted 480p talking clip with your actual product copy and an approved portrait.
2. One CPU Kokoro clip, comparing pronunciation and delivery to hosted speech.
3. One 480×832/81-frame Wan job on the 5070, recording peak VRAM/RAM and wall-clock time.
4. One InfiniteTalk clip on the selected cloud GPU, checking its complete source video, original audio and final cut.
5. An interrupted/resumed job and an invoice reconciliation before increasing batch size.
6. A small balanced benchmark scored by humans, then a limited publishing experiment with actual metrics.

Passing these establishes evidence for your selected configuration; it does not guarantee acceptance rates or a 3:1 LTV:CAC ratio at scale.
