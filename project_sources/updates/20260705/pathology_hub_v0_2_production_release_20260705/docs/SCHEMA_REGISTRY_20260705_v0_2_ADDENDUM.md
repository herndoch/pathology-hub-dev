# Schema Registry Addendum — Evidence Search Reliability v0_2 — 2026-07-05/06

## `evidence_search_response` schema versions observed in this release

Both `v1.5.9` and `v1.5.10` schema-version strings were observed in live API
responses during this release's verification (the underlying handler dispatches to
whichever internal version-generation block produced the response; `v1.5.10` appears
specifically when `render_html=true` triggers the HTML bundle code path, `v1.5.9`
otherwise). **v0_2 did not introduce a new schema_version string** — it adds fields
onto whichever of these the baseline handler already returns, per
`docs/API_CONTRACT_20260705_v0_2_ADDENDUM.md` (this package) for the exact field-level
delta.

| Schema version | Where observed |
|---|---|
| `evidence_search_response.v1.5.9` | Standard (non-HTML-bundle) `/evidence/search` responses, staging and production |
| `evidence_search_response.v1.5.10` | `render_html=true` responses (HTML bundle path), staging and production |

## `pathology_hub_health.v1.5.10`

`/health` schema, unchanged version string, with the new v0_2 boolean flags
(`evidence_v0_2_enabled`, `evidence_v0_2_module_loaded`,
`evidence_query_expansion_enabled`, `evidence_root_gating_enabled`,
`evidence_who_rerank_enabled`) and `evidence_v0_2_import_error` added as new,
additional fields (not a schema_version bump).

## `evidence_query_expansion_rules` — new versions this release

| Schema version | File | Status |
|---|---|---|
| `evidence_query_expansion_rules.v0_2` | `backend/query_expansion_rules_v0_2.json` | Original/audited baseline rule set, kept unmodified |
| `evidence_query_expansion_rules.v0_2_1` | `backend/query_expansion_rules_v0_2_1.json` | **Deployed to production.** Adds `allow_standalone` to 5 rules (SSL/CRC/AIS/SCCIS/CMF) and one new `NOS` title-boost-only rule |

## Benchmark schemas

| Schema version | Purpose |
|---|---|
| `evidence_retrieval_benchmark.v0_1` | Original v0_1 baseline benchmark (979/1008) |
| `evidence_retrieval_benchmark_staging_v0_2.v1` | This release's live staging benchmark run (996/1008, 12 misses) — `benchmark_v0_2/staging_run_cycle_1.json` (repo root) |

## Audit schemas (deploy/rollout)

| Schema version | Purpose |
|---|---|
| `backend_api_prod_snapshot_pre_v0_2.v1` | Phase 0 production snapshot before any v0_2 change |
| `production_deploy_v0_2.v1` | Phase 8/9 production deploy + rollout audit |
| `staging_health_debug_v0_2.v1` | Staging health-responsiveness incident diagnosis |
| `evidence_retrieval_benchmark_staging_v0_2_upload.v1` | Phase 7 staging benchmark GCS upload audit |
| `pathology_hub_env_var_names_redacted.v1` | Redacted env-var-name-only snapshots (never values) |

## No breaking schema changes

No existing schema_version string was retired, renamed, or given an incompatible
field change. All additions in this release are net-new, optional fields on
already-`additionalProperties: true` response schemas, or entirely new sibling rule
files (`v0_2_1` alongside, not replacing, `v0_2`).
