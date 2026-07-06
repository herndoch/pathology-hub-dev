# v0_2 Local Test Results — 2026-07-05

## Environment

Local Python virtual environment (`.venv_test/`, not committed) with `pytest`, `fastapi`,
`uvicorn`, `pydantic`, `google-cloud-storage`, `openai`, `pillow`, `numpy`, `faiss-cpu`
installed so that `backend/pathology_hub_v04_live_recovered/app.py` imports cleanly
(all imports resolve; no real GCS/OpenAI network calls are made because
`ensure_artifacts()` and friends only run from `@app.on_event("startup")` handlers,
which a plain module import does not trigger).

## Test suites run

```
$ .venv_test/bin/python -m pytest tests/ -v
```

Full output: `audits/local_test_results_20260705/pytest_output.txt`.

**Result: 50 passed, 0 failed.**

| Test file | Tests | Purpose |
|---|---|---|
| `tests/test_evidence_query_expansion_v0_2.py` | (pre-existing, 27 total across 3 files) | Core query expansion behavior |
| `tests/test_evidence_v0_2_regression_gate.py` | (pre-existing) | v0_1 hits preserved offline |
| `tests/test_evidence_root_gating_v0_2.py` | (pre-existing) | Root/blocked-root gating |
| `tests/test_backend_live_recovered_health.py` | 3 (new) | `/health` contract, v0_2 disabled/enabled, baseline-exception survival |
| `tests/test_backend_live_recovered_search_contract.py` | 2 (new) | `/evidence/search` response shape preserved |
| `tests/test_v0_2_server_side_flags.py` | 5 (new) | Each of the 4 flags actually changes server-side behavior (not a no-op) |
| `tests/test_v0_2_fallback_behavior.py` | 4 (new) | Fail-open guarantee: module import failure, expansion exception, dispatch-with-expanded-query exception (retries original), WHO rerank exception — all still return baseline results with an explicit warning |
| `tests/test_html_bundle_preservation.py` | 3 (new) | `render_html`/`html_profile` forwarded unchanged; non-dict HTML responses passed through untouched; HTML preserved when v0_2 disabled |
| `tests/test_figure_url_preservation.py` | 3 (new) | Figure URLs pass through unchanged; no leak when `include_figures=false`; WHO rerank does not touch `figures` field |
| `tests/test_source_status_contract.py` | 3 (new) | `source_status` values stay within the known contract; v0_2 never rewrites `source_status`; warnings are additive, not replacing |

27 (pre-existing) + 23 (new, itemized above) = 50.

## What these tests do NOT cover (explicitly out of scope for local/offline testing)

- Real retrieval quality (FTS/vector search results) — requires real GCS-backed indexes,
  covered by the Phase 6/7 staging deploy + live benchmark instead.
- Real WHO/PathOut/journal upstream API behavior — same reason.
- Actual HTML bundle rendering correctness (only the wrapper's pass-through behavior is
  tested locally) — covered by the Phase 6 staging HTML bundle smoke test.
- Cold-start / GCS artifact loading performance — covered by the Phase 6 staging health
  check (observed ~110s cold, <1s warm against the real production service in this
  session's Phase 0 snapshot).

## Config module change verified separately

`backend/evidence_search_reliability_v0_2/config.py`'s new `root_gating_enabled` field
and `backend/evidence_search_reliability_v0_2/query_expansion.py`'s `allow_standalone`
ordering fix were verified against the full pre-existing 27-test suite both before and
after the change (27/27 passing in both cases), plus a dedicated offline regression
replay against all 1008 cached v0_1/v0_2 benchmark queries (see
`docs/V0_2_1_RULE_CHANGELOG_20260705.md`) confirming the fix changes expansion decisions
for exactly the 24 intended rows and zero others.
