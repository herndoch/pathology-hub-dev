# Evidence Search Reliability v0_2 — Product Specification

**Version:** v0_2 (production-intended)  
**Date:** 2026-07-05  
**Workstream:** Evidence RAG / Backend API  
**External API surface:** Unchanged — single Action `searchEvidence` / `POST /evidence/search`  
**Status:** Local module complete; **server-side integration pending**

---

## User-facing problem

Pathologists and trainees query Pathology Hub with **short abbreviations and organ-specific terms** (LCIS, SSL, CIS, IPMN, CMF). The live API (v1.5.10) returns relevant evidence **97.1%** of the time in broad entity testing, but **abbreviation-only queries** drive most misses:

- Wrong-entity retrieval (e.g., SSL matching non-GI "secure sockets" context in textbook chunks)
- WHO under-performance (**92.1%** hit rate vs 100% journals)
- Organ-context collisions (CRC vs renal carcinoma family)
- Single `source_unavailable` error on IPMN + textbooks + `include_figures=true`

Users experience **silent near-misses**: HTTP 200 with plausible but wrong-root or wrong-entity excerpts. The Custom GPT must not compensate by inventing URLs, timestamps, or citations.

v0_2 turns the v0_1 engineering backlog into a **governed server-side reliability layer** — not a new Action, not client-side GPT prompt hacks.

---

## Goals and non-goals

### Goals

1. Reduce expected-hit misses from **28 → ≤14** (50% reduction) on the 35-entity v0_1 panel
2. Preserve v0_1 hits (**979/1008** minimum) — zero net regression gate
3. Improve WHO and abbreviation query types without new API fields exposed to GPT Builder
4. Maintain figure safety: no URLs when `include_figures=false`
5. Enable kill-switch rollback via environment variable

### Non-goals

- New GPT Actions or OpenAPI operations
- Curriculum tag browse API (separate tag-runtime workstream)
- Vector rebuilds or GCS promotion
- Automatic ABPath / v0_4 curriculum mutation
- C/AR/F map_status fields in API responses (explicitly forbidden in rules schema)

---

## Example entities (benchmark panel)

These entities anchor acceptance testing. Each has multiple query types: `exact_name`, `abbreviation`, `synonym`, `organ_context`.

| Entity ID | Display name | Root | Abbrev / risk token | v0_1 pain |
|-----------|--------------|------|---------------------|-----------|
| BREAST_003 | Lobular carcinoma in situ | Breast | **LCIS** | WHO abbreviation misses |
| GI_001 | Sessile serrated lesion | GI | **SSL** | WHO + textbook abbreviation misses |
| GI_002 | Colorectal adenocarcinoma | GI | **CRC** | Abbreviation + wrong-root risk |
| GU_003 | Urothelial carcinoma in situ | GU | **CIS** | Abbreviation misses |
| GYN_004 | Cervical adenocarcinoma in situ | GYN | **AIS** | Abbreviation misses |
| GI_004 | Intraductal papillary mucinous neoplasm | GI | **IPMN** | 1× source_unavailable with figures |
| GYN_003 | High-grade serous carcinoma | GYN | **HGSC** | Abbreviation context |
| SKIN_001 | Bullous pemphigoid | Skin | (exact name) | Lowest entity hit rate (75%) |
| SKIN_003 | Squamous cell carcinoma in situ | Skin | **SCCIS** | Abbreviation misses |
| BST_004 | Chondromyxoid fibroma | BST | **CMF** | Abbreviation misses |

Additional governed tokens in rules JSON: IDC, IDC NOS, ccRCC, pRCC, PTC, MTC, DSRCT, DFSP.

---

## Technical features

### 1. Query expansion

**Module:** `backend/evidence_search_reliability_v0_2/query_expansion.py`  
**Rules:** `backend/query_expansion_rules_v0_2.json`

Behavior:

- Detect governed abbreviations in query (token-boundary aware)
- Append expansions to dispatch query (`expansion_mode: append_query`)
- Respect `enabled`, `allow_standalone`, `required_context_terms`
- Never emit `map_status` or C/AR/F classification fields

Example rule (LCIS):

```json
{
  "abbreviation": "LCIS",
  "expansions": ["lobular carcinoma in situ"],
  "allowed_roots": ["Breast"],
  "required_context_terms": ["breast", "lobular", "mammary"],
  "expansion_mode": "append_query",
  "allow_standalone": true
}
```

Example rule (SSL — high ambiguity):

```json
{
  "abbreviation": "SSL",
  "expansions": ["sessile serrated lesion", "sessile serrated polyp"],
  "allowed_roots": ["GI"],
  "required_context_terms": ["colon", "colorectal", "rectum", "serrated", "polyp"],
  "blocked_roots": ["Cyto_Soft_Tissue"],
  "ambiguity_risk": "high"
}
```

### 2. Root inference

**Module:** `backend/evidence_search_reliability_v0_2/root_inference.py`

Behavior:

- Infer candidate curriculum roots from query tokens, organ terms, and optional entity metadata
- Gate expansions: only apply when inferred roots intersect `allowed_roots`
- Block expansions when query context matches `blocked_roots`
- Penalize cross-root retrieval in post-processing when organ context is explicit (CRC ≠ GU)

Outputs (internal diagnostics only unless debug env enabled):

- `inferred_roots[]`
- `expansion_applied: bool`
- `expansion_blocked_reason`

### 3. WHO rerank

**Module:** `backend/evidence_search_reliability_v0_2/who_ranking.py`

Behavior:

- After standard WHO upstream/passthrough results return, rerank `who_results`
- Boost exact/near-exact matches on entity title, chapter heading, subsection
- Apply abbreviation-aware matching when expansion was applied
- Do not fabricate WHO rows not returned by upstream

Addresses:

- BREAST_002 exact-name IDC NOS misses
- SKIN_001 bullous pemphigoid exact-name misses
- BREAST_003 / GI_001 / GI_002 abbreviation rows

### 4. Figure preservation

**Policy:** v0_2 must not alter figure behavior except by fixing the IPMN `source_unavailable` error path.

Proven v0_1 behavior to preserve:

| Setting | Expected |
|---------|----------|
| `include_figures=false` | Zero figure URLs in response (504/504 rows clean) |
| `include_figures=true` | Figure URLs only from API fields (`page_image_url`, `figure_url`, etc.) |
| Textbook figure proxy | Controlled TTL proxy; no invented URLs |

Regression guardrail: replay figure inventory comparison (`benchmark_figure_url_inventory.csv`).

Integration hook: `patch_search_response()` in `integration.py` — must not strip or add figure fields except via existing handler fixes.

---

## Request / response contract (unchanged externally)

GPT Builder continues using `openapi_pathology_hub_unified_searchEvidence_v1_5_8.yaml` (or current production schema) until explicit schema promotion.

Optional internal request preprocessing (transparent to client):

```python
dispatch_payload, expansion, diagnostics = preprocess_evidence_search_request(payload, config=cfg)
```

Optional internal response patch (WHO source only):

```python
response = patch_search_response(response, original_query=..., expansion=..., diagnostics=...)
```

Environment variables:

| Variable | Default (staging) | Purpose |
|----------|-------------------|---------|
| `EVIDENCE_QUERY_EXPANSION_ENABLED` | `true` | Master kill switch |
| `EVIDENCE_QUERY_EXPANSION_DEBUG` | `false` | Include diagnostics in logs only — never to GPT |
| `EVIDENCE_QUERY_EXPANSION_RULES_PATH` | bundled JSON path | Override rules file |

---

## Safety constraints

1. **One Action only** — no new endpoints
2. **No hallucinated URLs** — GPT instructions unchanged: use API-returned fields only
3. **No map_status in rules or responses** — C/AR/F remain curriculum audit concepts, not API fields
4. **Fail closed on ambiguous expansion** — if root inference conflicts, skip expansion rather than broaden query
5. **Forbidden tag patterns** — v10.5 governance must remain intact post-deploy
6. **No production deploy** without approval phrase `APPROVE_PRODUCTION_DEPLOY_EVIDENCE_SEARCH_V0_2`
7. **Rollback** — single env var disable + traffic shift to prior revision

---

## Staging validation plan

**Target service:** `pathology-hub-v04-curriculum-staging` (or dedicated evidence-staging — see master plan D1)

### Phase 1 — Deploy gate

- [ ] Recovered source integrated with v0_2 patch
- [ ] Container builds successfully
- [ ] Staging revision serves health 200
- [ ] `EVIDENCE_QUERY_EXPANSION_ENABLED=true` on staging only

### Phase 2 — Smoke (10 cases)

Run against staging base URL:

```bash
export PATHOLOGY_HUB_BASE="https://pathology-hub-v04-curriculum-staging-vorn5q2kga-uc.a.run.app"
export PATHOLOGY_HUB_API_KEY="<from Secret Manager — do not commit>"
python project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/codex_local/api_smoke_test.py
```

Plus v0_2-specific abbreviation probes (LCIS, SSL, IPMN).

### Phase 3 — Live v0_2 benchmark

```bash
python 06_audits/evidence_retrieval_writable/benchmark_v0_2/run_live_v0_2_benchmark.py \
  --base-url "$STAGING_URL" \
  --output-dir audits/benchmark_v0_2_staging/
```

Compare to v0_1 baseline CSV in `benchmark_v0_1/benchmark_results_summary.csv`.

### Phase 4 — Offline regression

```bash
python 06_audits/evidence_retrieval_writable/benchmark_v0_2/run_offline_v0_2_replay.py
```

Must preserve 979/979 v0_1 hits minimum.

### Phase 5 — Figure guardrail

- Re-run figure inventory diff
- Confirm IPMN GI_004 error resolved
- Confirm zero URLs with `include_figures=false`

Use wrapper: `commands/run_v0_2_staging_validation.sh`

---

## Production acceptance criteria

| Gate | Threshold | Measurement |
|------|-----------|-------------|
| Hit rate | ≥979/1008 AND misses ≤14 | Live benchmark on staging, then canary on production |
| v0_1 regression | 0 net lost hits vs baseline | `V0_1_TO_V0_2_DELTA.csv` — no regressions on release candidate |
| WHO source | ≥95% hit rate (stretch) | Source-level slice of benchmark |
| Abbreviation misses | ≤50% of v0_1 abbreviation miss count | Failure mode taxonomy |
| Figure leak | 0 unexpected URLs | Figure inventory guardrail |
| Forbidden tags | 0 in smoke payloads | v10.5 pattern scan |
| Unit tests | 100% pass | v0_2 test suite |
| Smoke tests | 10/10 pass | `_run_smoke_v0_2.sh` |
| Rollback drill | Env disable restores prior behavior | Staging verified |
| Approval | Phrase recorded | `FINAL_APPROVAL_REQUIRED.md` |

---

## Current status (2026-07-05)

| Item | Status |
|------|--------|
| Rules JSON | Complete — 20+ abbreviation rules |
| Unit tests | **27/27 PASS** |
| Smoke tests (against production API, client-side expansion) | **10/10 PASS** |
| v0_1 regression (offline) | **PASS** |
| Live v0_2 client-side benchmark | **979/1008** — 3 improved, 3 regressed, net zero |
| Miss target ≤14 | **FAILED** (29 misses) |
| Server-side staging deploy | **NOT DONE** |
| Production ready | **NO** |

---

## Implementation map

| Component | Path |
|-----------|------|
| Rules | `backend/query_expansion_rules_v0_2.json` |
| Config loader | `backend/evidence_search_reliability_v0_2/config.py` |
| Query expansion | `backend/evidence_search_reliability_v0_2/query_expansion.py` |
| Root inference | `backend/evidence_search_reliability_v0_2/root_inference.py` |
| WHO rerank | `backend/evidence_search_reliability_v0_2/who_ranking.py` |
| Integration | `backend/evidence_search_reliability_v0_2/integration.py` |
| Drop-in patch doc | `backend/pathology_hub_v04_curriculum/evidence_search_v0_2_patch.py` |
| Benchmark v0_1 baseline | `06_audits/evidence_retrieval_writable/benchmark_v0_1/` |
| Benchmark v0_2 | `06_audits/evidence_retrieval_writable/benchmark_v0_2/` |

---

## Known limitations

- Client-side expansion benchmark **does not prove** server-side behavior for Custom GPT Action
- Some expansions may require tuning after staging (SSL, CRC cross-root)
- WHO upstream remains passthrough — rerank cannot create missing upstream rows
- Bullous pemphigoid may need exact-name boost beyond abbreviation logic
- OpenAPI external schema unchanged — diagnostics not exposed to GPT
