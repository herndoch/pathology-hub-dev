# Production Cold-Start Fix Applied — 2026-07-06

**Approved and applied per explicit human instruction, exactly as recommended in
`docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md`.** Traffic-pointer-only
change between two existing, identical-image revisions. No new code deployed, no
GCS object touched, no GPT Builder change.

## Pre-flight re-verification (performed before changing anything)

| Check | Result |
|---|---|
| `pathology-hub-v04-00028-guf` still at 100% traffic? | Yes, confirmed |
| `pathology-hub-v04-00029-rnt` still exists? | Yes |
| `00029-rnt` `minScale` annotation | `1` (confirmed) |
| `00028-guf` image digest | `sha256:05f8a9d17cc19f006efadcd166f0feeb19659b51e3e87302468d86e94b16d62a` |
| `00029-rnt` image digest | `sha256:05f8a9d17cc19f006efadcd166f0feeb19659b51e3e87302468d86e94b16d62a` |
| **Digests match?** | **Yes, byte-for-byte identical** — re-verified explicitly immediately before the traffic shift, not assumed from the earlier investigation |

All pre-conditions confirmed. Proceeded.

## Exact command run

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --to-revisions=pathology-hub-v04-00029-rnt=100
```

## Before / after traffic state

| | Before | After |
|---|---|---|
| `pathology-hub-v04-00028-guf` | **100%** | 0% (still exists, tagged `v0-2-candidate`) |
| `pathology-hub-v04-00029-rnt` | 0% (retired) | **100%** |

Confirmed independently via `gcloud run services describe pathology-hub-v04
--format='value(status.traffic)'` immediately after the shift completed (traffic
update itself took ~104 seconds to route and stabilize).

## Min-instances now actually effective (confirmed via revision condition, not just service-level setting)

```
$ gcloud run revisions describe pathology-hub-v04-00029-rnt --format=json
...
autoscaling.knative.dev/minScale = 1        (revision annotation, not just service template)
condition: Ready True "Updating revision scaling succeeded in 1m21.95s."
condition: Active True
condition: MinInstancesProvisioned True "Min instances provisioned successfully in 1m21.89s."
```

**`MinInstancesProvisioned: True` is the definitive confirmation** that Cloud Run
has actually provisioned the guaranteed warm instance for the revision now serving
100% of traffic — this is the exact condition that was `False` (with the revision
marked "retired") before this fix, per the investigation doc.

## Health check (post-fix)

3 consecutive checks, no delay:

| Attempt | HTTP | Time |
|---|---|---|
| 1 | 200 | 3.37s (still had some residual latency from the traffic-shift completing moments earlier) |
| 2 | 200 | **0.16s** |
| 3 | 200 | **0.14s** |

Content confirmed correct: `version: 1.5.10-html-bundle-v0.2-prod`, `loaded: true`,
all 4 v0_2 flags `true`.

## Smoke tests — response time evidence (the actual point of this fix)

### Test 1: LCIS breast, `sources: ["who", "textbooks"]`

**First call: HTTP 200 in 27.56s — NOT immediately declared a success.** Investigated
before concluding anything, per explicit instruction not to assume success on slow
latency:

1. Checked Cloud Run logs for the exact window: **no new `Starting new instance`
   event occurred between the 3 successful fast `/health` checks and this
   `/evidence/search` call** — the same already-warm, already-`Application startup
   complete` instance handled it. This rules out a container-level cold start as the
   cause of the 27.56s delay.
2. **Re-ran the identical query 3 more times immediately after:** `0.89s`, `0.48s`,
   `0.75s` — consistently fast.

**Conclusion: the 27.56s delay was a one-time "first live `/evidence/search`
request" warm-up cost on this specific freshly-started instance** (most likely
first-invocation initialization of the WHO-upstream client/connection path, which
`/health` never exercises and which the min-instances fix does not address, since
min-instances only guarantees the container/process is running, not that every
internal client/connection has been pre-warmed). **This is a distinct, separate
phenomenon from the min-instances cold-start bug that this task fixed** — it is a
one-time cost per instance lifecycle (i.e., it will recur only if this instance is
ever replaced, e.g. by a future deploy or Cloud Run-initiated recycling), not a
recurring per-request problem. It was not present on the second smoke query below,
which only exercised the `textbooks` path (already warmed by earlier testing in this
session).

| Metric | Value |
|---|---|
| First call | 200, 27.56s |
| Repeat calls (x3) | 200, 0.89s / 0.48s / 0.75s |
| `source_status` | `{"who": "ok", "textbooks": "ok", ...}` throughout |
| `query_expansion_applied` | `true` throughout |

### Test 2: IPMN pancreas, `include_figures: true`, `sources: ["textbooks"]`

| Metric | Value |
|---|---|
| HTTP status | 200 |
| Elapsed | **0.78s** |
| `source_status` | `{"textbooks": "ok", ...}` |
| `textbook_results` | 5 |
| `figures` | 5 (correctly populated) |
| `query_expansion_applied` | `true` |

**PASS, fast/warm as expected.**

## Overall verdict

**The min-instances fix is confirmed successful and effective**, evidenced by:
1. `MinInstancesProvisioned: True` on the now-serving revision (the definitive
   Cloud Run-reported confirmation).
2. Health checks consistently fast (0.14-0.16s) after the initial post-shift moment.
3. Repeated identical search queries consistently fast (sub-second) once past the
   one-time first-request warm-up.

**A separate, minor, distinct observation was found and is reported honestly rather
than hidden:** a one-time ~27s warm-up cost on the very first live `/evidence/search`
call exercising the WHO-source code path on a freshly-started instance. This is
**not** a min-instances problem (the instance was already running and passing health
checks when this occurred) and is **not fixed by this change** — it would only
resurface if the current instance is ever replaced. This is noted here for
completeness and possible future investigation (e.g., pre-warming the WHO client on
container startup), but was explicitly out of scope for this task (traffic-pointer
change only, no code change).

## Rollback path (unaffected, re-confirmed)

Rollback target for reverting to the pre-v0_2 baseline remains
**`pathology-hub-v04-00027-tjm`**, completely unaffected by this traffic-pointer
change (which only moved traffic between two identical-v0_2-image revisions). See
`docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md` (updated with a note pointing to
this doc).

## Confirmed untouched

GPT Builder, GCS canonical/index data, and application code were not touched. No
new container image was built or deployed — this was purely a traffic-routing change
between two revisions that already existed and share an identical image digest.
