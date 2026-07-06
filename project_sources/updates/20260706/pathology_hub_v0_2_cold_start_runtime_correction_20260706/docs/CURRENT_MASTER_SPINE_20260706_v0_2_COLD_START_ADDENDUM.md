# Current Master Spine Addendum — v0_2 Cold-Start Runtime Correction — 2026-07-06

This addendum corrects **only the live-traffic-revision detail** recorded in
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/CURRENT_MASTER_SPINE_20260705_v0_2_ADDENDUM.md`.
Everything else in that document (backend source provenance, benchmark state,
accepted limitations, GPT Builder/API contract state, branch/merge state) is
unaffected and remains accurate.

## Current live production state (corrected)

- Service: `pathology-hub-v04`, project `pathology-annotation-project`, region
  `us-central1`.
- **Revision: `pathology-hub-v04-00029-rnt`** (was previously recorded as
  `pathology-hub-v04-00028-guf` in the 20260705 package — see "What changed and
  why" below).
- **Version: `1.5.10-html-bundle-v0.2-prod`** — **unchanged**.
- **Traffic: 100%** on `pathology-hub-v04-00029-rnt`.
- **Min-instances: 1, now confirmed actually effective** on the serving revision
  (Cloud Run status condition `MinInstancesProvisioned: True`).
- The current live Action remains `searchEvidence` / `POST /evidence/search` — one
  Action only, unchanged.

## What changed and why

`pathology-hub-v04-00028-guf` (the revision recorded as "current" in the 20260705
package) was found, via a follow-up read-only investigation, to have **no effective
`autoscaling.knative.dev/minScale` annotation** despite the Cloud Run *service-level*
setting showing `minScale=1`. This was because a prior `gcloud run services update
--min-instances=1` command caused Cloud Run to create a **new** revision
(`pathology-hub-v04-00029-rnt`) carrying the corrected annotation, but production
traffic remained pinned by explicit revision name to the older `00028-guf`, so the
new revision never received traffic and was marked "Revision retired." by Cloud Run.
**`00028-guf` and `00029-rnt` share an identical container image digest**
(`sha256:05f8a9d17cc19f006efadcd166f0feeb19659b51e3e87302468d86e94b16d62a`) — this is
a pure infrastructure/runtime detail, not a code defect, and required no application
code change to correct. Full diagnosis: `docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md`
(repo root).

The correction was a single traffic-pointer command, explicitly human-approved,
moving 100% of traffic to `pathology-hub-v04-00029-rnt`:

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00029-rnt=100 \
  --project=pathology-annotation-project --region=us-central1
```

Full application and verification: `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`
(repo root).

## Backend source provenance, benchmark state, accepted limitations

**Unchanged from the 20260705 package.** No new source recovery, no new benchmark
run, no new limitation decisions were made as part of this correction. Refer to
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/CURRENT_MASTER_SPINE_20260705_v0_2_ADDENDUM.md`
for those facts, which remain accurate as recorded.

## Rollback target

**Unchanged: `pathology-hub-v04-00027-tjm`** — the pre-v0_2 stable revision, still
exists, undeleted, at 0% traffic, completely unaffected by this correction (which
only moved traffic between two identical-v0_2-image revisions). Exact command:

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00027-tjm=100 \
  --project=pathology-annotation-project \
  --region=us-central1
```

## GPT Builder / API contract

**Unchanged.** GPT Builder was not opened or modified as part of this correction.
No OpenAPI/API schema change was required or made — this was a pure Cloud Run
traffic-routing change, invisible to the API contract. Exactly one Action remains:
`searchEvidence` / `POST /evidence/search`.

## Monitored-not-fixed observation (explicitly out of scope for this correction)

A one-time ~27-second warm-up delay was observed on the first live
`/evidence/search` call exercising the WHO-source code path against the newly
serving instance; immediate repeat calls were consistently sub-second (0.48-0.89s).
Logs confirmed no new container instance started during the slow call, ruling out a
container-level cold start as the cause — this is a distinct, separate,
first-request-per-instance-lifecycle phenomenon from the min-instances issue this
correction fixed, and was explicitly not addressed here. See
`docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md` (repo root) for full detail and
the reasoning for leaving it unaddressed at this time.
