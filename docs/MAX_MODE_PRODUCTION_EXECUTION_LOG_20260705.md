# Production V0_2 Recovery/Release — Execution Log (2026-07-05)

Running log of actual commands and results, phase by phase. Timestamps are UTC session-relative (see individual audit JSONs for exact UTC timestamps).

---

## Phase 0 — Safety snapshot

1. Created branch `production-v0-2-recovery-release-20260705` off `evidence-search-reliability-v0_2-prod` (prior HEAD).
2. Wrote `docs/CURSOR_TRUE_WSL_PREFLIGHT_20260705.md` (pwd, git, python3, gcloud versions/auth/config — no secrets).
3. Captured pre-session `git status --short` → `audits/local_workspace_snapshot_20260705/git_status_pre_production_agent.txt`.
4. Snapshotted production **before touching anything**:
   - `gcloud run services describe pathology-hub-v04 --region=us-central1 --format=export` → `audits/prod_snapshot_pre_v0_2_20260705/service.export.yaml`
   - `--format=json` → `service.describe.json`
   - `gcloud run revisions list` → `revisions.list.json`
   - Traffic: `{'latestRevision': True, 'percent': 100, 'revisionName': 'pathology-hub-v04-00027-tjm'}`
   - Image: `us-central1-docker.pkg.dev/pathology-annotation-project/pathology-hub/pathology-hub-v04:staging-html-v1-5-10-20260704-r3`
   - Image digest: `sha256:1d7480629887c8150d40c6de8115c9e48197908759c7fc70ef32e35112a88019`
   - Env var **names** only recorded (see `LIVE_RUNTIME_AND_CLOUDRUN_MAP_20260705.md`); no values printed.
   - Live `/health` called: HTTP 200, `version: 1.5.10-html-bundle`, `schema_version: pathology_hub_health.v1.5.10`, `loaded: true` → `audits/prod_snapshot_pre_v0_2_20260705/health_response.json`.
   - 5 real `/evidence/search` smoke calls (who/textbooks/pathout/journals/lectures) → all HTTP 200 → `audits/prod_snapshot_pre_v0_2_20260705/smoke_tests/*.json`. Summary: 5/5 pass, all `source_status: ok`, no errors, expected result counts.
5. Rollback target identified: current active revision **`pathology-hub-v04-00027-tjm`** at 100% traffic (this is also `latestReadyRevisionName`, i.e. current production state, unmodified by this session). Rollback command recorded in `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md`.
6. Non-secret snapshot parts uploaded to `gs://pathology_hub/06_audits/backend_api/prod_snapshot_pre_v0_2_20260705/` (additive only).

## Phase 1 — Recover live backend source

- Traced production image digest → Cloud Build history via `gcloud builds list` (22 builds), filtered for image tag match.
- Found exact build `8cd07783-a403-4cc7-a276-0c2b41c5ca37` (SUCCESS, 2026-07-05T01:12:37Z) that produced the **exact currently-serving image** (tag `staging-html-v1-5-10-20260704-r3`, digest matches production `service.describe.json` exactly).
- Build's `source.storageSource` pointed to `gs://pathology-annotation-project_cloudbuild/source/1783213953.082741-022523da066d4db4970f9cc151a3ff94.tgz`.
- Downloaded this tarball directly (read-only `gcloud storage cp`, no deploy) → `recovered_backend/v04_10_live_source/source.tgz`.
- Extracted: `app.py` (3202 lines), `Dockerfile`, `requirements.txt`, `.dockerignore`.
- **Verified exact match**: `app.py` contains `APP_VERSION_V1510 = "1.5.10-html-bundle"` at line 2718, matching live `/health` version string exactly. This is the **actual live production source**, not a reconstruction.
- See `docs/LIVE_BACKEND_RECOVERY_RESULTS_20260705.md` for full detail and confidence assessment.

## Phase 2 — Canonical recovered backend

- Built `backend/pathology_hub_v04_live_recovered/` from the verified `recovered_backend/v04_10_live_source/app.py` as the base (not the stale 1.5.7 copy).
- See `docs/LIVE_BACKEND_VS_LOCAL_1_5_7_RECONCILIATION_REPORT.md` and `docs/WHY_STALE_1_5_7_MUST_NOT_BE_PATCHED_DIRECTLY.md`.

## Phase 3 — v0_2 server-side integration

- See `docs/V0_2_SERVER_SIDE_INTEGRATION_DESIGN_20260705.md` and `docs/V0_2_SERVER_SIDE_INTEGRATION_DIFF_SUMMARY_20260705.md`.

## Phase 4 — Miss diagnostics

- See `docs/V0_2_29_MISS_DIAGNOSTIC_RESULTS_20260705.md`.

## Phase 5 — Local tests

- See `docs/V0_2_LOCAL_TEST_RESULTS_20260705.md`.

## Phase 6 — Staging deploy

- See `docs/STAGING_DEPLOY_LOG_V0_2_20260705.md`.

## Phase 7 — Staging benchmark

- Ran the full 1008-row v0_1 benchmark query set live against the deployed staging
  service (`pathology-hub-v04-v0-2-staging-00004-hvf`, v0_2 fully enabled).
  **Result: 996/1008 hits (98.81%), 12 misses** (down from the 979/1008 (29-miss)
  baseline). Target was <=14 misses — met with margin.
- Zero regressions: all 12 remaining misses are a strict subset of the original 29;
  0 figure leaks, 0 wrong-root/wrong-entity classifications, `source_status` "ok" on
  all 1008 rows. No cycle 2/3 tuning was needed.
- Full results: `benchmark_v0_2/staging_run_cycle_1.json` (summary),
  `benchmark_v0_2/staging_run_cycle_1/` (raw CSV/JSON, raw JSON gzipped for repo size),
  uploaded to `gs://pathology_hub/06_audits/evidence_retrieval/v0_2_staging_20260705/`.
- See `docs/V0_2_STAGING_BENCHMARK_RESULTS_20260705.md`,
  `docs/V0_2_REMAINING_MISS_REGISTER_20260705.md`, and
  `docs/V0_2_GO_NO_GO_DECISION_20260705.md` (recommendation: **GO**, all 7 gates met).
- Also produced (not executed): `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md` and
  `docs/PROPOSED_PRODUCTION_DEPLOY_PLAN_V0_2_20260705.md` for human review before any
  future Phase 8.

## Interim: staging health responsiveness investigation (between Phase 6 and Phase 7)

- Repo owner reported staging `/health` appearing to hang. Diagnosed root cause
  (scale-to-zero cold start, ~80-90s, inherited from production's own architecture —
  not a v0_2 defect), fixed via `--min-instances=1` (staging only), and re-ran the
  Phase 6 forced-fallback test safely (async deploy + bounded polling, avoiding an
  earlier CLI hang). See `docs/STAGING_HEALTH_DEBUG_V0_2_20260705.md` and
  `docs/STAGING_REDEPLOY_FIX_LOG_V0_2_20260705.md`. Resolved in 1 cycle. Production
  confirmed untouched throughout (re-verified at the end of Phase 7: still revision
  `pathology-hub-v04-00027-tjm` at 100% traffic).

## Session end state

Stopped after Phase 7 per the mission's hard scope boundary. Phase 8 (production
deploy/traffic shift) was NOT started. Phase 9/10 (GPT Builder packaging, release ZIP)
were skipped as explicitly low-priority/optional under the budget constraint.

(This log is appended to as each phase completes; see individual phase docs for full command transcripts and JSON evidence.)
