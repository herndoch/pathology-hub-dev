# Production Release Safety Rules — Evidence Search Reliability v0_2 (2026-07-05)

These rules govern this entire session (Phases 0–7) and were established before any recovery, integration, or deploy work began.

## Absolute prohibitions (this session)

1. **No deploy, update, or traffic-shift on `pathology-hub-v04`** (production). Read-only `describe`/`list` only.
2. **No GCS object deletion** anywhere, ever, in any bucket.
3. **No overwrite of canonical/normalized records or indexes** in `gs://pathology_hub` or `gs://pathology-hub-0`.
4. **No new GPT Action / operationId.** Exactly one Action remains: `searchEvidence` / `POST /evidence/search`.
5. **No GPT Builder mutation.** Out of scope entirely.
6. **No Docker.** Use Cloud Build / `gcloud run deploy --source` / `gcloud builds submit` only.
7. **No secret values printed or committed.** Only env var **names** appear in any snapshot, log, or doc. Secret values (API keys) are held only in the local shell environment for the duration of a command and never written to disk in this repo.
8. **No force-push, no other-branch mutation.** All work happens on `production-v0-2-recovery-release-20260705`.
9. **No progression into Phase 8** (production deploy/traffic shift) under any circumstance in this session, even if all gates pass. Phase 7 output is a recommendation package for human review only.

## Required before any GCS upload

Every upload must be preceded by an audit JSON containing at minimum:
- `schema_version`
- `input_paths`
- `output_paths`
- `counts`
- `known_limitations`

Uploads are **additive only** — new objects under `gs://pathology_hub/06_audits/...`. Never `gsutil rm`, never overwrite existing canonical objects.

## Staging deploy rules

- New Cloud Run service only (`pathology-hub-v04-v0-2-staging` or similar), never `pathology-hub-v04` itself.
- Feature flags default to safe values; `EVIDENCE_V0_2_ENABLED` etc. are staging-only toggles.
- Staging must fall back to baseline behavior if v0_2 internals fail — verified with a forced-failure test.

## Retry/stop discipline

- Max 3 failed deploy/test cycles per step without a new hypothesis before stopping and documenting.
- Max 3 benchmark tuning cycles in Phase 7 before stopping regardless of outcome.

## Rollback readiness

The exact rollback command for current production is recorded in `docs/LIVE_RUNTIME_AND_CLOUDRUN_MAP_20260705.md` and `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md`. It must be verified to still be current (revision name unchanged) before any future Phase 8 execution — this session does not execute it, only records it.
