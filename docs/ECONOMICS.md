# Benchmarking and economics

## What to optimize

Optimize expected contribution after acquisition, rather than raw cost per generated file:

```text
Contribution LTV = average order value × lifetime purchases × contribution margin
All-in CAC = (media spend + production spend) / newly acquired customers
LTV:CAC = contribution LTV / all-in CAC
Expected contribution = new customers × contribution LTV − media − production
Maximum CAC for a 3:1 target = contribution LTV / 3
```

Contribution margin should include product cost, shipping, payment fees, returns and other variable costs before acquisition. The app does not estimate your actual repeat-purchase behavior. Input supported assumptions, then update them from customer cohorts. Expected lifetime contribution is not booked cash profit, and excludes fixed overhead and time value of money.

The example product is deliberately fictional. Its $32 order value, 1.4 lifetime purchases and 50% contribution margin imply $22.40 contribution LTV and $7.47 maximum CAC for 3:1. The app supplies no fake conversions or profitable sample results.

## Correct paid funnel math

```text
Media CAC = CPM / (1,000 × CTR × click-to-new-customer conversion rate)
```

Rates are fractions. At $12 CPM, 1.5% CTR and 3% conversion, media CAC is **$26.67**, before creative allocation. A lower video-generation bill alone will not turn that into $7.47 CAC. Offer, customer value, landing page and conversion matter.

For organic posting, media spend may be zero. Creative production still has a cost, and attribution still needs new-customer measurement. A zero-cost demo must not be used to infer production acquisition economics.

## Hosted baseline

As checked on 2026-11-23, Fabric is listed at $0.08/second for 480p and $0.15/second for 720p. Therefore:

| Generated avatar duration | 480p base video | 720p base video |
| --- | ---: | ---: |
| 15 seconds | $1.20 | $2.25 |
| 20 seconds | $1.60 | $3.00 |
| 30 seconds | $2.40 | $4.50 |

These are the video endpoint alone, before portrait/speech, failures or changes to provider rates. The app reserves extra buffer. It measures audio duration before asking for video. A nominal 15-second script can be shorter or longer depending on speech delivery. [Fabric pricing](https://fal.ai/models/veed/fabric-1.0).

The original notes' much lower monthly examples are hypotheses, not the system's measured budget. At 1,000 fresh 15-second Fabric generations, the base avatar endpoint alone would be $1,200 or $2,250 at those rates. Reusing product footage and approved assets changes that mix substantially.

## Self-hosting break-even

```text
Raw generation cost = GPU hourly cost × elapsed GPU seconds / 3,600
Cost per accepted clip = total run cost / number of accepted clips
```

Include rejected and failed attempts. Add startup, model loading, idle rental, storage, transfers and electricity where applicable. A successful HTTP response is not an acceptance decision. The app's runtime-based estimate is useful for screening, not an invoice.

For a purely illustrative $0.75/hour GPU, a 10-minute generation costs $0.125 before overhead. At 50% acceptance, this becomes $0.25 per accepted clip before overhead. This is arithmetic, **not a runtime estimate for InfiniteTalk or your 5070**.

For your own PC, estimate electricity from measured wall power and elapsed time, and optionally allocate hardware cost. `UGC_LOCAL_HOURLY` is configurable because location, power cost and utilization differ. Default $0.10/hour is only a placeholder. Current default local-Wan reservations conservatively charge one configured hour until you reconcile them; do not confuse that with measured inference runtime.

## A useful pilot

1. Verify one clip per route and record the exact worker image/model revision, dimensions, frame count, steps, GPU, RAM and driver.
2. Generate balanced matched prompts across the two or three plausible routes. Start small enough to stay inside your budget; expand only after basic quality and memory fit are known.
3. Review blinded clips for realism, identity, lip-sync, product accuracy, motion, caption timing and source consistency. The UI records 1–5 scores on three core dimensions; use notes for the rest.
4. Reconcile provider invoices. Separate first-load/cold costs from steady batches. Compare total cost per **approved** video, not fastest generation or cheapest attempt.
5. Publish a manageable set of distinct approved creatives, preserving creative IDs/UTMs. Import daily metrics. Use consistent new-customer definitions and attribution windows.
6. Reserve most iteration for promising routes while retaining an explicit exploration budget. Avoid increasing ad spend automatically from a handful of organic views.

Use `scripts/benchmark.py` to generate the matched batch JSON. It never submits inference itself. A model experiment holds script/creator/seed constant inside each model block. A quality tier comparison between Fabric 480p and 720p answers a resolution/cost question; comparing either with InfiniteTalk answers an architecture/deployment question. Wan B-roll/remix are different creative formats and should be analyzed as formats, not identical talking-head replacements.

## Interpreting the dashboard

CTR uses total clicks divided by total impressions, with a Wilson 95% interval. It is not the arithmetic average of individual clip CTRs. The app deliberately does not call a winner based on non-overlapping intervals or a fixed conversion threshold. It labels sparse-conversion evidence exploratory, and larger samples descriptive pending controlled distribution.

Platform algorithms choose who sees a creative; organic results may differ because of timing, audience and delivery. Ad-platform allocation can also confound comparisons. Hundreds of simultaneous tests increase false discoveries. For spending decisions, use a preplanned randomized test where possible, a meaningful minimum detectable effect and an appropriate multiple-testing or sequential framework. This implementation supplies the raw IDs, matched production inputs and descriptive summaries, not an automated causal inference engine.

Costs include pending reserves and all attempts assigned to the group; that makes a running batch look temporarily expensive. Cached identity/footage cost is assigned to the first batch that generated it. Use the whole factory ledger or a documented amortization adjustment for long-run comparisons. Record actual bills before deciding to scale a self-hosted deployment.
