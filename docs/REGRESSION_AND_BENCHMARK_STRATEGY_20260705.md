# Regression and Benchmark Strategy

**Date:** 2026-07-05  
**Workstream:** Evidence RAG / QA  
**Baseline:** Evidence Retrieval Benchmark v0_1 (live, completed 2026-07-05)

---

## Strategy overview

Pathology Hub QA uses a **layered evidence model**:

1. **Smoke tests** — fast, live API, forbidden-tag and health gates
2. **Live benchmark** — 35-entity panel, 1,008 query/source rows, expected-hit scoring
3. **Offline replay** — re-score saved JSON without API calls
4. **Guardrail suites** — figure leaks, wrong-root, source-unavailable
5. **Regression gate** — v0_2 must preserve v0_1 hits before promotion

No layer alone proves production readiness. Live benchmark + offline regression + smoke must align.

---

## Smoke tests

### Purpose

Catch deploy-breaking failures in <2 minutes.

### Script locations

| Script | Purpose |
|--------|---------|
| `project_sources/.../codex_local/api_smoke_test.py` | v10.5 forbidden-tag scan (3 payloads) |
| `06_audits/evidence_retrieval_writable/evidence_search_reliability_v0_2_production_readiness/SMOKE_TEST_PLAN.md` | v0_2 smoke (10 cases) |
| `scripts/_run_smoke_v0_2.sh` | v0_2 wrapper (if present) |

### Standard v10.5 payloads

```json
{"query":"melanoma invasive overview","sources":["lectures"],"max_results":5,"compact":true,"excerpt_char_limit":900}
```

```json
{"query":"ovarian high grade serous carcinoma p53 BRCA","sources":["who","textbooks","pathout","journals"],"max_results":5,"compact":true,"excerpt_char_limit":900}
```

```json
{"query":"prostate adenocarcinoma cribriform pattern 4","sources":["textbooks","pathout"],"max_results":5,"compact":true,"excerpt_char_limit":900}
```

### Pass criteria

- Health GET → 200
- All POST → 200
- Forbidden primary-tag count = 0 for patterns: `::Lectures::`, `::Textbooks::`, `Slide_`, `Page_`, `Digital_Pathology_Slide`, `Pathology_Slide`, `Benign_Cystic_Neck_Mass_Case_01`, `::Error`

---

## Live benchmark

### v0_1 panel (canonical baseline)

| Metric | Value |
|--------|-------|
| Entities | 35 (Breast, GI, GU, GYN, Skin, BST, HN) |
| Query types | exact_name, abbreviation, synonym, organ_context |
| Sources | who, pathout, textbooks, journals |
| Figure variants | include_figures true/false per row |
| Total rows | 1,008 |
| Expected hits | 979 (97.1%) |
| Misses | 28 + 1 error |

**Artifacts:** `06_audits/evidence_retrieval_writable/benchmark_v0_1/`

| File | Purpose |
|------|---------|
| `benchmark_entities_v0_1.csv` | Entity panel |
| `benchmark_results_raw.json` | Full API responses |
| `benchmark_results_summary.csv` | Row-level scoring |
| `benchmark_figure_url_inventory.csv` | Figure URL audit |
| `benchmark_expected_hits_v0_1.json` | Expected hit definitions |

### v0_2 live benchmark

**Runner:** `06_audits/evidence_retrieval_writable/benchmark_v0_2/run_live_v0_2_benchmark.py`

**Current result (client-side expansion against production URL):**

- Hits: 979/1008 (unchanged)
- Improved: 3 (LCIS/WHO ×2, IPMN/textbooks+figures)
- Regressed: 3 (net zero)
- Misses: 29

**Staging requirement:** Re-run against staging URL after server-side deploy.

### Miss-reduction target

| Metric | v0_1 | v0_2 target | Current v0_2 |
|--------|------|-------------|--------------|
| Misses | 28 (+1 err) | **≤14** | 29 — **FAIL** |
| Hit rate | 97.1% | ≥98.6% | 97.1% |
| WHO hit rate | 92.1% | ≥95% | not improved (client-side) |

Formula: 50% miss reduction from 28 ≈ 14 allowed misses.

---

## Offline replay limits

### What offline replay CAN do

- Re-score v0_1 raw JSON with new expansion logic (`run_offline_v0_2_replay.py`)
- Verify **no regression** on previously found hits (979/979 preserved — PASS)
- Compare figure URL inventories without network
- Run 10/10 regression tests reading saved CSV/JSON only

### What offline replay CANNOT do

- Prove server-side integration in Cloud Run handler
- Validate WHO upstream behavior changes from rerank applied in production path
- Catch latency, timeout, or `source_unavailable` transient errors
- Prove Custom GPT Action behavior (client-side expansion ≠ Action path)
- Replace staging live benchmark before production

**Rule:** Offline PASS is necessary but not sufficient for production promotion.

---

## Wrong-root guardrail

### Definition

Retrieval returns excerpts whose curriculum root or content domain does not match query organ context (e.g., SSL → informatics TLS; CRC query → renal cell content).

### Detection

Benchmark row scoring + manual review of abbreviation query_type misses:

| Entity | Token | Risk |
|--------|-------|------|
| GI_001 | SSL | Cyto/informatics collision |
| GI_002 | CRC | GU renal collision |
| GU_003 | CIS | HN/Breast CIS collision |
| GYN_004 | AIS | GI glandular collision |

### Guardrail test (automated where possible)

For abbreviation rows, check `primary_tag` root prefix or excerpt keywords against `allowed_roots` in `query_expansion_rules_v0_2.json`.

### Pass criteria

- Wrong-root miss count ≤ v0_1 baseline after v0_2 deploy
- Zero new wrong-root regressions in `V0_1_TO_V0_2_DELTA.csv`

---

## Figure regression guardrail

### v0_1 proven behavior

| Condition | Expected |
|-----------|----------|
| `include_figures=false` | 0 figure URLs in 504 rows |
| `include_figures=true` | URLs only in API figure fields |

### Guardrail script logic

```python
for row in summary_csv:
    if row["include_figures"] == "False":
        assert row["figure_url_count"] == 0, row
```

### IPMN special case

- v0_1 error: GI_004 / IPMN / textbooks / include_figures=true / `source_unavailable`
- v0_2 must resolve or document as known limitation with audit entry

---

## Source-unavailable guardrail

### Definition

`source_status` or row status indicates source error despite health ok.

### v0_1 baseline

- 1 row: GI_004, IPMN, textbooks, include_figures=true

### Pass criteria for v0_2

- Source-unavailable count ≤ v0_1 (target: 0)
- No new errors on previously passing rows

---

## Suggested output schemas

### benchmark_run_audit.json

```json
{
  "schema_version": "evidence_retrieval_benchmark_audit.v1",
  "generated_at_utc": "2026-07-05T22:00:00Z",
  "benchmark_version": "v0_2",
  "base_url": "https://pathology-hub-v04-curriculum-staging-vorn5q2kga-uc.a.run.app",
  "api_ran": true,
  "health_status": "ok",
  "service_version": "1.5.10-html-bundle-v0_2",
  "entity_count": 35,
  "total_runs": 1008,
  "expected_hits_found": 993,
  "misses": 14,
  "errors": 0,
  "hit_rate": 0.986,
  "source_hit_rates": {
    "who": {"hits": 240, "total": 252, "rate": 0.952},
    "pathout": {"hits": 250, "total": 252, "rate": 0.992},
    "textbooks": {"hits": 251, "total": 252, "rate": 0.996},
    "journals": {"hits": 252, "total": 252, "rate": 1.0}
  },
  "guardrails": {
    "figure_leak_count": 0,
    "wrong_root_new_regressions": 0,
    "source_unavailable_count": 0,
    "forbidden_tag_count": 0
  },
  "input_paths": [
    "06_audits/evidence_retrieval_writable/benchmark_v0_1/benchmark_entities_v0_1.csv"
  ],
  "output_paths": [
    "06_audits/evidence_retrieval_writable/benchmark_v0_2/benchmark_v0_2_results_raw.json",
    "06_audits/evidence_retrieval_writable/benchmark_v0_2/benchmark_v0_2_results_summary.csv"
  ],
  "known_limitations": [
    "Staging only; production not promoted."
  ]
}
```

### benchmark_results_summary.csv (columns)

```csv
entity_id,entity_name,root,query,query_type,source,include_figures,status,expected_hit_found,failure_mode,retrieval_mode,journal,primary_tag,figure_url_count,vector_score,fts_rank,expansion_applied,expansion_terms,v0_1_hit,v0_2_hit,delta
```

### benchmark_failure_analysis.json

```json
{
  "schema_version": "benchmark_failure_analysis.v1",
  "failure_mode_counts": {
    "expected_hit_found": 993,
    "expected_source_present_but_not_retrieved": 14,
    "source_unavailable": 0,
    "wrong_root_retrieval": 2
  },
  "abbreviation_misses_by_entity": {
    "GI_001": 2,
    "GI_002": 2
  },
  "top_regressions": []
}
```

### regression_test_results.json

```json
{
  "schema_version": "evidence_regression_suite.v1",
  "run_at_utc": "2026-07-05T22:35:00Z",
  "mode": "offline",
  "tests_run": 10,
  "tests_passed": 10,
  "tests_failed": 0,
  "cases": [
    {"id": "REG-001", "name": "v0_1_hit_preservation", "pass": true},
    {"id": "REG-002", "name": "figure_leak_false", "pass": true}
  ]
}
```

---

## Execution cadence

| When | Run |
|------|-----|
| Every backend revision (staging) | Smoke + offline regression |
| Pre-production | Full live benchmark v0_2 |
| Post-deploy canary (24h) | Smoke every 4h + abbreviated 5-entity panel |
| After governance promotion | v10.5 forbidden-tag smoke |
| Monthly | Full 35-entity live benchmark read-only |

---

## Safety constraints

- Read-only live benchmark against production unless explicitly approved
- Never store API keys in benchmark JSON
- Do not upload to GCS without audit JSON and approval
- Do not rebuild vectors as part of benchmark
- Writable outputs only under `06_audits/evidence_retrieval_writable/`

---

## Related artifacts

- `06_audits/evidence_retrieval_writable/benchmark_v0_1/review_package/` — human review bundle
- `06_audits/evidence_retrieval_writable/benchmark_v0_2/V0_1_TO_V0_2_DELTA.csv` — per-row delta
- `docs/EVIDENCE_SEARCH_RELIABILITY_V0_2_PRODUCT_SPEC.md` — acceptance criteria
- `commands/run_v0_2_staging_validation.sh` — staging wrapper
