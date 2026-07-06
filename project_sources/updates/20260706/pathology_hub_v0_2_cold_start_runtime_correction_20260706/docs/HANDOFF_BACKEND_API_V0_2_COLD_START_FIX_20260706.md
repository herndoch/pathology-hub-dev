# Handoff — Backend API / v0_2 Cold-Start Runtime Correction — 2026-07-06

**Status: correction applied and verified.** This is a complete, standalone handoff
for this specific runtime correction — it supplements, and does not replace,
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/HANDOFF_BACKEND_API_EVIDENCE_SEARCH_RELIABILITY_V0_2_PROD_20260705.md`,
which remains the primary handoff for the v0_2 release itself.

## 1. What is live right now

| Field | Value |
|---|---|
| Service | `pathology-hub-v04` |
| Project | `pathology-annotation-project` |
| Region | `us-central1` |
| **Current revision** | **`pathology-hub-v04-00029-rnt`** (corrected from `pathology-hub-v04-00028-guf`) |
| **Version string** | **`1.5.10-html-bundle-v0.2-prod`** (unchanged) |
| **Traffic** | **100%** on `pathology-hub-v04-00029-rnt` |
| **Min-instances** | **1, now confirmed actually effective** (`MinInstancesProvisioned: True`) |
| GPT Action | `searchEvidence` / `POST /evidence/search` (one only, unchanged) |

Verify yourself:

```bash
gcloud run services describe pathology-hub-v04 \
  --project=pathology-annotation-project --region=us-central1 \
  --format='value(status.traffic)'

gcloud run revisions describe pathology-hub-v04-00029-rnt \
  --project=pathology-annotation-project --region=us-central1 \
  --format='value(status.conditions)'
```

## 2. What problem this corrects

The v0_2 production release (`project_sources/updates/20260705/...`) recorded
`pathology-hub-v04-00028-guf` as the serving revision with `min-instances=1`. A
follow-up investigation found this was **not actually true at the revision level**:
`00028-guf` never had an effective `minScale` annotation, even though the Cloud Run
*service*-level setting appeared correct. This caused intermittent cold-start delays
(30-110+ seconds) on `/health` and `/evidence/search` under otherwise light traffic.

## 3. Root cause (full detail: `docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md`, repo root)

A prior `gcloud run services update --min-instances=1` command caused Cloud Run to
create a **new** revision (`pathology-hub-v04-00029-rnt`) carrying the corrected
`minScale=1` annotation. However, production traffic had been pinned by **explicit
revision name** (`--to-revisions=pathology-hub-v04-00028-guf=100`, from the original
Phase 9 rollout) rather than tracking "latest," so the new revision never received
any traffic and Cloud Run marked it "Revision retired." The revision that was
actually serving all traffic (`00028-guf`) could never receive the setting, because
**Cloud Run revisions are immutable** — an existing revision's scaling annotation
cannot be changed in place.

**This is purely a Cloud Run traffic-routing/infrastructure detail. It is not an
application code defect** — `00028-guf` and `00029-rnt` share an identical container
image digest (`sha256:05f8a9d17cc19f006efadcd166f0feeb19659b51e3e87302468d86e94b16d62a`).

## 4. The fix (full detail: `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`, repo root)

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --to-revisions=pathology-hub-v04-00029-rnt=100
```

A pure traffic-pointer change between two existing, identical-image revisions. No
new container was built or deployed.

## 5. Verification performed

- Pre-flight: re-confirmed `00028-guf` still at 100%, `00029-rnt` still existed with
  `minScale=1`, and both revisions' image digests were re-verified byte-for-byte
  identical immediately before the change (not assumed from the earlier
  investigation).
- Post-fix: confirmed traffic 100% on `00029-rnt`; confirmed
  `MinInstancesProvisioned: True` on the revision's own Cloud Run status condition
  (the definitive signal, not just the service-level setting); confirmed `/health`
  returns 200 with correct version and all 4 v0_2 flags true, consistently fast
  (0.14-0.16s) after the initial post-shift moment.
- Smoke tests: IPMN pancreas (+figures, textbooks) was fast and correct (0.78s). LCIS
  breast (who+textbooks) returned 200 in 27.56s on the **first** call — this was
  **investigated, not assumed to be a fix failure**: logs confirmed no new container
  instance started during that call (ruling out a cold start), and 3 immediate
  repeat calls were consistently sub-second (0.48-0.89s). Concluded this is a
  separate, one-time, first-live-request warm-up cost on the WHO-source code path,
  not the min-instances issue, and explicitly left unaddressed as out of scope for
  this correction.

## 6. Rollback (unaffected)

`pathology-hub-v04-00027-tjm` remains the full pre-v0_2 rollback target, completely
unaffected by this correction:

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00027-tjm=100 \
  --project=pathology-annotation-project \
  --region=us-central1
```

## 7. Not yet done / explicit next steps

1. **Continue monitoring** for the WHO first-live-request warm-up observation (see
   section 5). No fix is proposed or scheduled at this time; it is a minor,
   one-time-per-instance-lifecycle cost, not a recurring problem.
2. Everything else from the 20260705 handoff's "not yet done" list remains
   applicable and unaffected by this correction (merge to `master`, v0_3 backlog
   tickets, etc. — see `docs/NEXT_SAFE_WORK_ORDER_AFTER_V0_2_20260706.md`, repo
   root).

## 8. Where everything lives (repo root, unless noted)

- Investigation: `docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md`,
  `audits/cold_start_investigation_20260706/`
- Fix application: `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`,
  `audits/cold_start_fix_20260706/`
- Updated rollback plan: `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md` (updated
  with a note pointing to this correction)
- This package:
  `project_sources/updates/20260706/pathology_hub_v0_2_cold_start_runtime_correction_20260706/`
