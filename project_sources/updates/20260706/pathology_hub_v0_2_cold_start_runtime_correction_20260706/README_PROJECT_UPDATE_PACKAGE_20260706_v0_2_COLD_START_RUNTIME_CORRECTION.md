# Pathology Hub — Project Source Update Package — 2026-07-06 — v0_2 Cold-Start Runtime Correction

Generated: 2026-07-06 (session-relative; see `docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md`
and `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md` at the repo root for exact
command transcripts and timestamps).

This package follows the same location convention as
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/`
(dated top-level folder -> named package folder -> `docs/` subfolder for
addendum-style documents, with this README at the package root as the entry point).

## Scope of this package — read this first

**This package is a narrow runtime-detail correction, not a new release.** It
supersedes **only** the live-traffic-revision and min-instances detail recorded in
the 20260705 package (`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/`).
It does **not** change, retract, or supersede anything else from that package:

- Production code version is unchanged: **`1.5.10-html-bundle-v0.2-prod`**.
- The staging benchmark result (996/1008, 12 misses) is unchanged.
- The two accepted-limitation decisions (BREAST_002/NOS, GU_005 — both explicitly
  reviewed and approved by Charlie, tracked for v0_3) are unchanged.
- The API contract, schema, and GPT Builder state are unchanged.

**What changed:** production traffic now points at a different Cloud Run revision
than the 20260705 package recorded, because a runtime/infrastructure issue (not a
code defect) meant the originally-recorded revision never actually had its
min-instances setting take effect. This has since been diagnosed and corrected. See
below for the exact before/after.

## Read in this order

1. `docs/HANDOFF_BACKEND_API_V0_2_COLD_START_FIX_20260706.md` — the complete standalone handoff for this correction
2. `docs/CURRENT_MASTER_SPINE_20260706_v0_2_COLD_START_ADDENDUM.md` — what changed in the canonical current-state summary
3. `docs/WORKSTREAM_STATUS_20260706_v0_2_COLD_START.md` — workstream status
4. `docs/DECISIONS_LOG_20260706_v0_2_COLD_START_ADDENDUM.md` — decisions made and by whom
5. `docs/GPT_INSTRUCTIONS_DELTA_V0_2_COLD_START_20260706.md` — confirms no GPT Builder action needed (consistent with the 20260705 package's GPT instructions delta)

## Critical current state (as of end of this correction, 2026-07-06)

- **Production `pathology-hub-v04` is live on revision `pathology-hub-v04-00029-rnt`**
  (not `pathology-hub-v04-00028-guf`, which the 20260705 package recorded),
  **100% traffic**.
- **`pathology-hub-v04-00029-rnt` and `pathology-hub-v04-00028-guf` share an
  identical container image digest** (`sha256:05f8a9d17cc19f006efadcd166f0feeb19659b51e3e87302468d86e94b16d62a`)
  — this is the same v0_2 application code, not a new deploy.
- **Production code version is unchanged: `1.5.10-html-bundle-v0.2-prod`.**
- **`pathology-hub-v04-00029-rnt` is the revision where `min-instances=1` is now
  actually effective**, confirmed via Cloud Run's own `MinInstancesProvisioned: True`
  status condition (previously `False` on `00029-rnt` before the traffic shift, and
  never achievable at all on `00028-guf`, whose `minScale` annotation was absent and
  can never be added since Cloud Run revisions are immutable).
- **`pathology-hub-v04-00028-guf` should now be understood as the prior v0_2 revision
  that had no effective `minScale` on serving traffic** — a runtime/infrastructure
  detail, not a code defect. It is retired from traffic (0%) but its container image
  is identical to the currently-serving revision.
- **Full pre-v0_2 rollback target is unchanged: `pathology-hub-v04-00027-tjm`.** Exact
  command:
  ```bash
  gcloud run services update-traffic pathology-hub-v04 \
    --to-revisions=pathology-hub-v04-00027-tjm=100 \
    --project=pathology-annotation-project --region=us-central1
  ```
- **GPT Builder remains unchanged.** Exactly one Action: `searchEvidence` /
  `POST /evidence/search`. No API/OpenAPI schema change was required for this
  correction (it is a pure Cloud Run traffic-routing change, invisible to the API
  contract).
- **No GCS canonical/index changes were made** at any point in this correction.
- **Monitored-not-fixed observation, explicitly out of scope for this correction:**
  a one-time ~27-second warm-up delay was observed on the very first live
  `/evidence/search` call exercising the WHO-source code path against a freshly
  serving instance; repeat identical calls immediately afterward were consistently
  sub-second. This is a distinct phenomenon from the min-instances issue this
  correction fixed (the instance was already running and passing health checks when
  the slow call occurred) and was not addressed here. See
  `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md` (repo root) for full detail.

## Included in this package

Addendum-style documents (`docs/`) only. This package references, rather than
duplicates, the full raw evidence, which lives at the repo root under
`docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md`,
`docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`, and
`audits/cold_start_investigation_20260706/` / `audits/cold_start_fix_20260706/`.

## Not included

- Raw Cloud Run `describe`/log JSON evidence (see the repo-root `audits/` paths above).
- Any secret values. All docs reference env var/secret **names** only, never values.
- Any change to GPT Builder, OpenAPI YAML files, Cloud Run services beyond the
  traffic-pointer change already applied and documented, or GCS canonical/index data.
