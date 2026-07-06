# Pathology Hub — Project Source Update Package — 2026-07-05/06 — Evidence Search Reliability v0_2 Production Release

Generated: 2026-07-06 (session-relative; see individual docs and `docs/MAX_MODE_PRODUCTION_EXECUTION_LOG_20260705.md`
at the repo root for exact UTC timestamps of each step).

This package follows the same location convention as
`project_sources/updates/20260704/pathology_hub_handoff_local_codex_20260704_v3/`
(dated top-level folder -> named package folder -> `docs/` subfolder for
addendum-style documents, with this README at the package root as the entry point).

## Read in this order

1. `docs/HANDOFF_BACKEND_API_EVIDENCE_SEARCH_RELIABILITY_V0_2_PROD_20260705.md` — the complete standalone handoff
2. `docs/CURRENT_MASTER_SPINE_20260705_v0_2_ADDENDUM.md` — what changed in the canonical current-state summary
3. `docs/WORKSTREAM_STATUS_20260705_v0_2.md` — per-workstream status
4. `docs/DECISIONS_LOG_20260705_v0_2_ADDENDUM.md` — decisions made and by whom
5. `docs/API_CONTRACT_20260705_v0_2_ADDENDUM.md` — contract delta vs. the existing v1.5.9/v1.5.10 contract docs
6. `docs/SCHEMA_REGISTRY_20260705_v0_2_ADDENDUM.md` — schema versions involved
7. `docs/GPT_INSTRUCTIONS_DELTA_V0_2_20260705.md` — GPT Builder instruction guidance (not executed, GPT Builder untouched)

## Critical current state (as of end of session, 2026-07-06)

- **Production `pathology-hub-v04` is live on revision `pathology-hub-v04-00028-guf`**
  (`version: 1.5.10-html-bundle-v0.2-prod`), **100% traffic**, **min-instances=1**.
- Evidence Search Reliability v0_2 (query expansion, root gating, WHO rerank) is
  **truly server-side integrated in production** — not a client-side simulation.
- Live staging benchmark (same 1008-row set as the v0_1 baseline): **996/1008 (98.81%),
  12 misses**, down from **979/1008 (29 misses)**, with **zero regressions**.
- Two remaining miss categories were explicitly reviewed and accepted by the repo
  owner (Charlie) as known limitations, tracked for v0_3 follow-up work, not attempted
  further this release: **BREAST_002/NOS** (attempted WHO title-boost fix,
  unsuccessful — a retrieval-pool issue, not a reranking issue) and **GU_005**
  (a general WHO ranking limitation, not attempted this release).
- Rollback target: **`pathology-hub-v04-00027-tjm`** (the pre-v0_2 stable revision,
  still exists, undeleted, at 0% traffic). Exact command in
  `docs/HANDOFF_BACKEND_API_EVIDENCE_SEARCH_RELIABILITY_V0_2_PROD_20260705.md` and
  the repo root's `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md`.
- **API contract unchanged**: exactly one GPT Action, `searchEvidence` /
  `POST /evidence/search`. No new operations, no schema break. GPT Builder itself was
  **not** opened or modified in this release.
- The git branch carrying all of this work, `production-v0-2-recovery-release-20260705`,
  was independently verified merge-ready (8 commits ahead of `master`, zero
  divergence, all release-package checksums verified) but **has not yet been merged**
  — merge is pending Charlie's explicit approval and action (see
  `docs/MERGE_READINESS_V0_2_20260705.md` at the repo root).

## Included in this package

Addendum-style documents (`docs/`) only — this package references, rather than
duplicates, the full raw evidence (audits, benchmark data, deploy logs), which lives
at the repo root under `docs/`, `audits/`, `benchmark_v0_2/`, and
`release_artifacts/pathology_hub_v0_2_production_release_20260705/` (the formal
release ZIP with manifest and SHA256SUMS).

## Not included

- Raw benchmark JSON/CSV data (36MB+ combined) — see
  `benchmark_v0_2/staging_run_cycle_1/` at the repo root, or the compressed copy
  committed to git (`benchmark_results_raw.json.gz`).
- Any secret values (API keys). All docs in this package reference only env var
  **names** and Secret Manager secret **names**, never values.
- Any change to GPT Builder itself, OpenAPI YAML files, Cloud Run services, or GCS
  canonical/index data — this package is documentation only.
