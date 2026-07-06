# Handoff — Backend API / Evidence Search Reliability v0_2 — Production Release

**Date:** 2026-07-05 / 2026-07-06
**Workstream:** Backend API / Evidence RAG
**Status:** **LIVE IN PRODUCTION.** This is a complete, standalone handoff for anyone
picking up this workstream from here — it does not assume you have read the prior
session's chat transcript, only this document and the repo-root docs it cites.

---

## 1. What is live right now

| Field | Value |
|---|---|
| Service | `pathology-hub-v04` |
| Project | `pathology-annotation-project` |
| Region | `us-central1` |
| **Current revision** | **`pathology-hub-v04-00028-guf`** |
| **Version string** | **`1.5.10-html-bundle-v0.2-prod`** |
| **Traffic** | **100%** on this revision |
| **Min-instances** | **1** |
| GPT Action | `searchEvidence` / `POST /evidence/search` (one only, unchanged) |
| Auth | Header `X-API-Key` (Secret Manager: `pathology-hub-api-key`) |

Verify any of the above yourself before trusting it, via:

```bash
gcloud run services describe pathology-hub-v04 \
  --project=pathology-annotation-project --region=us-central1 \
  --format='value(status.latestReadyRevisionName,status.traffic)'

curl -sS https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/health
```

## 2. What changed to get here

1. **Backend source recovery.** The live production source (previously undocumented
   beyond a stale local `1.5.7` copy) was recovered by tracing the serving image
   digest to its exact Cloud Build source tarball — a genuine recovery, not a
   reconstruction, confirmed against live `/health`. Result:
   `backend/pathology_hub_v04_live_recovered/` (repo root) is the canonical
   deployable tree, and it is what is now live in production.
2. **v0_2 server-side integration.** Evidence Search Reliability v0_2 (governed
   abbreviation query expansion, anatomic root gating, WHO title/subsection
   reranking) — previously only a local module tested via client-side benchmark
   replay against the production API — is now wired directly into the recovered
   backend's `/evidence/search` and `/health` handlers, behind 5 feature flags, with
   a fail-open guarantee (see section 4).
3. **A real bug was found and fixed** in the pre-existing v0_2 module
   (`evidence_search_reliability_v0_2/query_expansion.py`): the `allow_standalone`
   escape hatch for single-anatomic-root abbreviations was unreachable due to gate
   ordering. Fixing it (plus adding `allow_standalone: true` to 5 rules in a new
   `query_expansion_rules_v0_2_1.json`) resolved 14 of the original 29 benchmark
   misses.
4. **Staging validation, then production rollout**, both explicitly human-approved at
   each major step (see the decisions log in this package).

## 3. Feature flags (all currently `true` in production except debug)

| Flag | Production value |
|---|---|
| `EVIDENCE_V0_2_ENABLED` | `true` |
| `EVIDENCE_QUERY_EXPANSION_ENABLED` | `true` |
| `EVIDENCE_ROOT_GATING_ENABLED` | `true` |
| `EVIDENCE_WHO_RERANK_ENABLED` | `true` |
| `EVIDENCE_V0_2_DEBUG` | `false` |
| `EVIDENCE_QUERY_EXPANSION_RULES_PATH` | `/app/query_expansion_rules_v0_2_1.json` |
| `EVIDENCE_HUB_APP_VERSION_OVERRIDE` | `1.5.10-html-bundle-v0.2-prod` |

Confirmed live via `/health` at the end of this release (all 4 boolean flags `true`,
`evidence_v0_2_import_error: null`).

## 4. Fail-open safety contract (verified, not just designed)

If `EVIDENCE_V0_2_ENABLED=false`, behavior is byte-identical to the recovered 1.5.10
baseline. If v0_2 is enabled but fails internally at any stage (module import,
query expansion, dispatch with an expanded query, WHO rerank), the baseline result is
still returned with an explicit warning string appended — **no source becomes
unavailable solely because v0_2 fails.** Verified via:
- 4 dedicated unit tests (`tests/test_v0_2_fallback_behavior.py`, repo root) that
  directly monkeypatch each failure point.
- A live forced-fallback test on staging (flip `EVIDENCE_V0_2_ENABLED=false`,
  confirm baseline behavior, flip back, confirm v0_2 behavior resumes).

## 5. Benchmark result

Live full-corpus benchmark (same 1008-row query set as the historical v0_1 baseline)
run directly against the deployed staging service (not an offline replay):

| | v0_1 baseline | v0_2 (this release) |
|---|---|---|
| Hits | 979/1008 | **996/1008** |
| Misses | 29 | **12** |
| Hit rate | 97.1% | **98.81%** |
| Regressions | — | **0** |

12 remaining misses, all documented, all a strict subset of the original 29:
- 6 rows: Bullous pemphigoid — true corpus gap (not a WHO tumour entity), not
  attempted.
- 2 rows: `CIS` standalone — intentionally left gated (3 plausible anatomic roots,
  genuine ambiguity), not attempted.
- 2 rows: GU_005 general WHO ranking limitation — not attempted this release
  (accepted as a known limitation, tracked for v0_3).
- 2 rows: BREAST_002/NOS — an attempted WHO title-boost fix did not resolve it
  (accepted as a known limitation, tracked for v0_3).

Full detail: `docs/V0_2_STAGING_BENCHMARK_RESULTS_20260705.md` and
`docs/V0_2_REMAINING_MISS_REGISTER_20260705.md` (repo root).

## 6. Rollback

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00027-tjm=100 \
  --project=pathology-annotation-project \
  --region=us-central1
```

`pathology-hub-v04-00027-tjm` (the pre-v0_2 stable revision) still exists, undeleted,
at 0% traffic. Re-verify this is still true before relying on it — it was correct as
of the end of this release, but revisions/traffic can change if anyone else deploys.

## 7. Tests

- 50/50 local unit tests passing (27 pre-existing v0_2 tests + 23 new, covering
  health/search contract, all 4 feature flags, fail-open fallback, HTML bundle
  preservation, figure URL preservation, source_status contract). Run with:
  `pytest tests/ -v` (repo root; needs a venv with fastapi/pydantic/google-cloud-storage/
  openai/pillow/numpy/faiss-cpu installed — see `docs/V0_2_LOCAL_TEST_RESULTS_20260705.md`).
- Live smoke tests (10-query suite: WHO/textbooks/journals/pathout/lectures/videos +
  figures + HTML bundle) passing on both staging and production.

## 8. Not yet done / explicit next steps

1. **Merge `production-v0-2-recovery-release-20260705` into `master`.** Independently
   verified merge-ready (clean fast-forward, zero divergence, checksums verified) but
   **not yet merged** — this requires Charlie's explicit manual action. See
   `docs/MERGE_READINESS_V0_2_20260705.md` (repo root) for the exact commands.
2. File the two v0_3 follow-up tickets (BREAST_002/NOS retrieval-pool investigation;
   GU_005 general WHO ranking-weight tuning).
3. Monitor production for the standard 24h post-deploy window.
4. Optionally apply the GPT instruction refinement suggested in
   `GPT_INSTRUCTIONS_DELTA_V0_2_20260705.md` (this package) — requires manual GPT
   Builder action, not done by any agent session.
5. Run the manual GPT Preview test script
   (`docs/GPT_BUILDER_V0_2_FRONTEND_TEST_SCRIPT_20260705.md`, repo root) for
   end-to-end frontend confirmation.

## 9. Where everything lives (repo root, unless noted)

- Deployable source: `backend/pathology_hub_v04_live_recovered/`
- v0_2 module: `backend/evidence_search_reliability_v0_2/` (also copied into the
  deployable tree above)
- Tuned rules: `backend/query_expansion_rules_v0_2_1.json`
- Tests: `tests/test_*_v0_2*.py`, `tests/test_backend_live_recovered_*.py`,
  `tests/test_html_bundle_preservation.py`, `tests/test_figure_url_preservation.py`,
  `tests/test_source_status_contract.py`
- Benchmark: `benchmark_v0_2/`
- Docs: all `docs/*_V0_2_*` and `docs/PRODUCTION_*` files listed in
  `docs/MAX_MODE_PRODUCTION_EXECUTION_LOG_20260705.md`
- Formal release package: `release_artifacts/pathology_hub_v0_2_production_release_20260705/`
- Audits: `audits/prod_snapshot_pre_v0_2_20260705/`, `audits/staging_*_20260705/`,
  `audits/prod_deploy_20260706/`, `audits/prod_traffic_shift_20260706/`,
  `audits/prod_min_instances_fix_20260705/`
- GCS: `gs://pathology_hub/06_audits/{backend_api,evidence_retrieval}/{prod_snapshot_pre_v0_2_20260705,v0_2_staging_20260705,v0_2_staging_debug_20260705,v0_2_production_20260705}/`
