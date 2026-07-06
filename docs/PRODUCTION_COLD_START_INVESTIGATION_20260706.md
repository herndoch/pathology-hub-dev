# Production Cold-Start Investigation — 2026-07-06

**Read-only investigation. No Cloud Run setting, GCS object, or GPT Builder
configuration was changed while producing this report.**

## Conclusion (read this first)

**Root cause found, with conclusive evidence: `min-instances=1` was successfully
applied by Cloud Run, but only to a brand-new revision (`pathology-hub-v04-00029-rnt`)
that never received any production traffic, because traffic is pinned by explicit
revision name (not tracking "latest") from the Phase 8/9 rollout. The revision that
is actually serving 100% of traffic, `pathology-hub-v04-00028-guf`, still has
`minScale` unset (effectively 0) and always will, because Cloud Run revisions are
immutable — its scaling annotation can never be changed in place.** This is not a
propagation-delay issue, not a concurrency/scale-out issue under light load, not an
OOM/crash issue, and not a startup-probe misconfiguration. It is a traffic-routing
gap between the "current settings" (service-level desired state) and the "current
serving revision" (an older, immutable revision that predates the setting).

---

## Checklist findings (in the order requested)

### 1. Is `min-instances=1` actually still set? (re-confirmed, read-only)

**Yes, at the service level — but this is exactly the misleading part.**
`gcloud run services describe pathology-hub-v04 --format=json` still shows
`spec.template.metadata.annotations["autoscaling.knative.dev/minScale"] = "1"`.
This represents Cloud Run's **desired configuration for the next revision**, not
necessarily a property of the currently-serving revision.

Checking the **actual serving revision's own annotations** directly
(`gcloud run revisions describe pathology-hub-v04-00028-guf`) shows **no `minScale`
annotation at all** (absent, which Cloud Run treats as the default, effectively 0).

### 2. Actual current instance count

Not directly queryable via a single read-only command in this environment (no
Cloud Monitoring time-series query tool available in this session), but inferred
conclusively from Cloud Run's own revision status conditions on the retired revision
`pathology-hub-v04-00029-rnt`: **`MinInstancesProvisioned: False`**. This confirms
Cloud Run itself considers the min-instance guarantee **not provisioned** for the
service right now, consistent with the serving revision (`00028-guf`) having no
`minScale` and the revision that DOES have `minScale=1` (`00029-rnt`) being marked
`Active: False, "Revision retired."` (i.e. not running any instances because it
receives 0% traffic).

### 3. Longer log window (2h) — pattern analysis

Pulled 175 log entries over the last 2 hours (`audits/cold_start_investigation_20260706/logs_2h.json`).
Exactly **4** `Starting new instance` events, all explainable:

| Timestamp (UTC) | Reason | Explanation |
|---|---|---|
| 13:33:44 | `DEPLOYMENT_ROLLOUT` | The Phase 8 candidate deploy itself (expected, one-time) |
| 13:35:18 | `AUTOSCALING` | Shortly after deploy — `00028-guf` had no `minScale` from the start, so it scaled to zero almost immediately after the initial rollout instance was no longer needed, then had to cold-start again for the next request |
| 14:55:33 | `AUTOSCALING` | During this session's prior health-check probing — cold start #1 |
| 14:56:08 | `AUTOSCALING` | ~35s later — cold start #2 (a second instance, likely because the first cold-starting instance hadn't finished booting yet when the next probe arrived, so Cloud Run started a second one rather than queue-wait for the first) |

**None of these are `MANUAL_OR_CUSTOMER_MIN_INSTANCE` events** (the reason string
Cloud Run uses when a min-instance-guaranteed warm instance is being (re)provisioned
— this exact reason string WAS observed on staging's logs when its min-instances fix
was working correctly, for comparison; see `docs/STAGING_REDEPLOY_FIX_LOG_V0_2_20260705.md`).
Its total absence here across the full 2h window is itself strong evidence that no
min-instance guarantee is active on whatever revision is actually serving traffic.

This rules out hypothesis (a) "hasn't propagated yet" as the primary explanation —
the setting has had ~50+ minutes to propagate, and the true blocker (traffic pinned
to an older revision) will never resolve on its own no matter how long you wait.

### 4. Concurrency / max-instances

`containerConcurrency: 160`, `maxScale: 10` — both confirmed unchanged and correctly
configured on the serving revision. This rules out hypothesis (b): concurrency=160
is far more than enough for light sequential smoke-test traffic to stay on a single
instance; concurrency is not the cause of the observed scale-out. The scale-out
observed is a pure cold-start-from-zero event, not a concurrency-driven
horizontal-scale-out event.

### 5. Memory/CPU / OOM check

Zero OOM or memory-exceeded log entries in the 2h window. Zero `ERROR`-severity log
entries. Zero crash-related log text. This rules out hypothesis (e) in the form of
"the warm instance is being OOM-killed" — there is no warm instance to kill, and no
evidence of any container failure at all. Resources (`4 CPU / 12Gi memory`) are
unchanged from the values already proven sufficient throughout this release.

### 6. Recent revision/config changes around the slow-response times

This is the actual finding (see "Conclusion" above and the revision timeline table
below). The relevant recent changes are:

| Revision | Created (UTC) | `minScale` | Traffic | Status |
|---|---|---|---|---|
| `pathology-hub-v04-00027-tjm` | 2026-07-05 03:00:00 | `None` | 0% (rollback target) | Ready, undeleted |
| `pathology-hub-v04-00028-guf` | 2026-07-06 13:33:22 | **`None`** | **100% (currently serving)** | Ready, Active |
| `pathology-hub-v04-00029-rnt` | 2026-07-06 14:06:59 | **`1`** | **0%** | Ready, **"Revision retired."** |

`00029-rnt` has the **exact same image digest** as `00028-guf`
(`sha256:05f8a9d17...b16d62a`) — it is not a code change, purely a scaling-annotation
revision, created automatically by Cloud Run when the
`gcloud run services update --min-instances=1` command was run in the prior task.
**Every revision in this service's history back to `00002` (2026-06-21) carries its
own `minScale` annotation directly on the revision object** — this confirms that, for
this project/API version, min-instances changes are implemented by Cloud Run as a
new-revision creation, not a true in-place mutation of a live revision, even though
the command completed without needing `--no-traffic`/`--tag` and even though
`services describe`'s top-level traffic and `latestReadyRevisionName` fields did not
obviously flag this to the operator at the time.

## Why this was hard to notice at the time

In the prior "apply min-instances fix" task, verification checked
`status.latestReadyRevisionName` and `status.traffic` and saw `pathology-hub-v04-00028-guf`
in both, with the `minScale=1` annotation visible in `spec.template.metadata.annotations`
(the service's *desired* config) — which looked like confirmation that `00028-guf`
itself now had the setting. It does not. The revision that received the annotation
(`00029-rnt`) was created moments later but never got assigned to `latestReadyRevisionName`
or any percentage of traffic, because the traffic split had been explicitly pinned to
`pathology-hub-v04-00028-guf` by name during the Phase 9 rollout
(`--to-revisions=pathology-hub-v04-00028-guf=100`), rather than configured to track
"LATEST." A `services describe` snapshot alone, without also independently checking
`gcloud run revisions describe <the-actual-serving-revision-name>`, could not have
caught this — which is exactly why this follow-up investigation was warranted.

## Recommendation (for a human to approve and execute — NOT done by this task)

**This is a real, fully-diagnosed anomaly, not something to wait out.** No amount of
additional waiting will fix it, because `pathology-hub-v04-00028-guf`'s scaling
annotation can never change (revisions are immutable). Two options, in order of
preference:

1. **(Recommended, lowest risk)** Shift traffic to the already-existing
   `pathology-hub-v04-00029-rnt` revision, which is bit-for-bit the same container
   image as `00028-guf` (verified identical image digest) and already carries the
   correct `minScale=1`:
   ```bash
   gcloud run services update-traffic pathology-hub-v04 \
     --to-revisions=pathology-hub-v04-00029-rnt=100 \
     --project=pathology-annotation-project --region=us-central1
   ```
   Since the image is identical to what is already running, this carries the same
   risk profile as any other traffic-split command already used successfully
   throughout this release (i.e., very low — no new code, no new build). This would
   need to be re-verified with a health + smoke check afterward, the same pattern
   already used throughout Phases 6-9.
2. **(Alternative)** Re-run `gcloud run deploy` (or `services update`) with
   `--min-instances=1` specified explicitly as part of a command that also updates
   `latestReadyRevisionName`/traffic together, to avoid the split-state that occurred
   this time.

**Either way, a human should decide and approve before execution** — this
investigation task is explicitly read-only and did not implement either option.

## Files referenced

- `audits/cold_start_investigation_20260706/service.describe.json`
- `audits/cold_start_investigation_20260706/revision.describe.json` (`00028-guf`)
- `audits/cold_start_investigation_20260706/revision_00029.describe.json` (`00029-rnt`)
- `audits/cold_start_investigation_20260706/revisions.list.json` (full history, all 29 revisions)
- `audits/cold_start_investigation_20260706/logs_2h.json`
