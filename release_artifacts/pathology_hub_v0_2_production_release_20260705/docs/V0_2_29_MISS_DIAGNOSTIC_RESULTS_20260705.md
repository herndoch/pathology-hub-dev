# v0_2 29-Miss Diagnostic Results — 2026-07-05

## Method

Replayed the cached raw API responses from the prior session's live client-side v0_2
benchmark run (`06_audits/evidence_retrieval_writable/benchmark_v0_2/benchmark_v0_2_results_raw.json`,
1008 rows) through the same scoring logic used to produce the original 979/1008 (29-miss)
number (`06_audits/evidence_retrieval/benchmark_v0_1/benchmark_lib.py`:
`classify_failure` + `hit_matches_expected`). This is an **offline replay — zero new live
API calls** — implemented in `benchmark_v0_2/replay_miss_diagnostics.py`, output at
`benchmark_v0_2/miss_diagnostics_20260705.jsonl`.

Result: **29/1008 misses reproduced exactly**, confirming the diagnostic replay is
faithful to the originally-reported baseline before any tuning was attempted.

## Classification (29 misses -> 12 distinct entity/source root causes)

| Category | Count | Entities | Root cause |
|---|---|---|---|
| **Abbreviation expansion never fires for standalone queries** | 16 | GI_001 (SSL, 4 rows), GI_002 (CRC, 4 rows), GYN_004 (AIS, 2 rows), SKIN_003 (SCCIS, 2 rows), BST_004 (CMF, 2 rows), GU_003 (CIS, 2 rows) | Real bug in `evidence_search_reliability_v0_2/query_expansion.py`: the `allow_standalone` escape hatch was unreachable because the `root_allowed` gate ran first and always rejects when zero organ-context words are present (which is exactly the standalone case). **Fixed** for 5 of 6 (SSL/CRC/AIS/SCCIS/CMF each have exactly one `allowed_root`, so standalone inference is safe). CIS has 3 allowed roots (GU/GYN/Skin) — standalone inference would be a genuine ambiguity risk, left gated intentionally (accepted limitation, not "fixed"). |
| **WHO 5th-edition terminology mismatch** | 2 | BREAST_002 ("Invasive ductal carcinoma, NOS") | WHO Classification of Tumours 5th edition uses "invasive carcinoma of no special type (NST)," not "NOS." Added a title-boost-only alias rule (`NOS` -> `no special type`/`NST`, breast-context-gated) so WHO reranking can surface the correctly-titled entity without rewriting the dispatched query text. |
| **True corpus gap (non-tumour entity, not a bug)** | 6 | SKIN_001, Bullous pemphigoid (exact_name x2, entity_plus_organ x2, entity_plus_morphology x2) | Bullous pemphigoid is a benign autoimmune blistering disease, not a WHO Classification of Tumours entity. It is reasonable that the WHO tumour corpus has no matching record. **No fix attempted** — documented as a true corpus gap per mission instructions ("verify no source is claimed indexed/tagged without proof"; the WHO corpus proof shows this entity is legitimately absent, not mis-retrieved). |
| **Ranking failure on entity_plus_morphology query type** | 2 | GU_005 ("Nephrogenic adenoma tubular architecture") | Top WHO hits were "Villous adenoma" / "Tubular adenoma" (token overlap on "adenoma"/"tubular" outcompetes the correct, less lexically similar "Nephrogenic adenoma" entity). Not an abbreviation issue; would require a more general title-boost heuristic change with broader regression risk than justified by 2 rows. **Documented as a known ranking limitation, not fixed this session** to avoid overfitting to a single query pattern (see mission instruction: "do not overfit blindly to the 29 known misses at the expense of the other 979 passes"). |
| **source_unavailable (transient/infra, not a v0_2 concern)** | 3 | BREAST_001 (textbooks), BST_005 (textbooks), HN_001 (journals) | These were `source_status: error` at the time of the ORIGINAL live benchmark run against production. Notably, the recovered 1.5.10 source (this session's Phase 1/2 finding) already contains a `try/except` fallback around textbook vector search that did not exist at whatever revision ran the original benchmark — see `docs/LIVE_BACKEND_VS_LOCAL_1_5_7_RECONCILIATION_REPORT.md`. It is plausible (not yet proven) that the 2 textbook `source_unavailable` misses would already behave differently (FTS-only fallback with a warning, rather than a hard failure) on the currently-recovered source. This will be checked empirically in the Phase 7 staging benchmark. The journals miss (HN_001) is unrelated to any code in this session's scope (upstream journal API dependency) and is left as a known limitation. |

**Total: 16 + 2 + 6 + 2 + 3 = 29.** ✓

## Action taken

- Fixed the `allow_standalone` bug (targets 14 of 16 abbreviation-miss rows: SSL, CRC,
  AIS, SCCIS, CMF; CIS intentionally left gated).
- Added one new WHO terminology alias rule (targets 2 rows: BREAST_002).
- **Did not** attempt entity-specific fixes for the true corpus gap (6 rows) or the
  general ranking-limitation row (2 rows), per the mission's anti-overfitting
  instruction.
- **Optimistic best case if all targeted fixes work in the live staging benchmark:**
  29 -> 13 misses (14 abbreviation rows + 2 NOS rows resolved), which would clear the
  mission's `<=14` target. This is a projection based on offline expansion-decision
  replay, not yet a live-verified number — see `docs/V0_2_STAGING_BENCHMARK_RESULTS_20260705.md`
  for the actual Phase 7 result.

See `docs/V0_2_1_RULE_CHANGELOG_20260705.md` for the exact rule diffs and the
regression-safety check (confirms these changes affect ONLY the 24 targeted
query/source pairs among all 1008 cached benchmark rows, zero unintended changes).
