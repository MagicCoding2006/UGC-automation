---
name: pipeline-operator
description: Operate and troubleshoot ReelForge batches, GPU workers, cost reconciliation, schedules and exports through this repository's API and CLI.
---

Use `scripts/ugc.py doctor` and `state` before changing a live queue. Read `docs/DEPLOYMENT.md` for the selected worker, and `docs/OPERATIONS.md` for job states, reconciliation and backup boundaries. Resolve paths from the repository root. Keep tokens in `.env`/environment and out of output.

Use the UI/API for mutations rather than editing SQLite while workers run. Submit repeatable automation with a stable `Idempotency-Key`; retain it across network retries. Keep local video inference serial on 12 GB VRAM. CPU speech can run separately without loading a GPU model.

On a paid submission with an unknown response, inspect the retained request and provider dashboard. Attach the existing request ID when available. Only clear an unknown request after evidence that no provider job was submitted; otherwise leave the job in attention state. Resume from cached stages after resolving the cause, rather than creating an unexplained new generation.

Batch/daily reserves do not guarantee the provider invoice. Record actual bills through reconciliation, preserve failed-attempt costs, and include startup, idle and storage when comparing deployments. Raise a cap only within the user's authorized spending envelope.

Verify a completed result with technical QA, human review where required, and an approved export package. Do not call a GPU image verified until it ran with real model weights on the intended hardware. Back up database and media before a migration; preserve the separate model volumes when useful. Do not create cloud resources, publish posts or change ad spend unless requested.
