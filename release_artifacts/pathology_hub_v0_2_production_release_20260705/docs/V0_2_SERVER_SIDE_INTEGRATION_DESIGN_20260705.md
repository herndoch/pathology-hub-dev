# v0_2 Server-Side Integration Design — 2026-07-05

## Goal

Move Evidence Search Reliability v0_2 (query expansion, root gating, WHO rerank) from
"client-side replay against the production API" to "actually runs inside the request
path of `/evidence/search`," behind feature flags, with a hard guarantee that v0_2
failures never remove a source from availability.

## Where it hooks in

The recovered `app.py` (`backend/pathology_hub_v04_live_recovered/app.py`) removes and
re-registers `/health` and `/evidence/search` once per version generation (1.5.3 → 1.5.5
→ 1.5.6 → 1.5.7 → 1.5.8 → 1.5.9 → 1.5.10), with each generation's handler calling into
the previous one as its baseline (`_OLD_SEARCH_ENDPOINT_V1510` etc.), so only the LAST
registered route for a given path/method is ever reachable through FastAPI's router.

This session added **one more generation** on top, following the exact same pattern
already used by the recovered source itself:

```
1.5.3 -> 1.5.5 -> 1.5.6 -> 1.5.7 -> 1.5.8 -> 1.5.9 -> 1.5.10 -> [NEW] v0_2 wrapper
```

1. Capture the fully-formed v1.5.10 `/health` and `/evidence/search` endpoints as
   `_BASELINE_HEALTH_ENDPOINT_V02` / `_BASELINE_SEARCH_ENDPOINT_V02` (these already
   include HTML bundle, curriculum, figures, PathOut/lecture tags — everything).
2. Remove those two routes from `app.router.routes` (same idiom the recovered file
   already uses six times).
3. Register new `/health` and `/evidence/search` handlers that call the captured
   baseline functions and layer v0_2 behavior on top **only when explicitly enabled**.

This means the wrapper is purely additive: zero lines of the recovered 1.5.10 baseline
logic were modified, moved, or deleted.

## Request-path flow when `EVIDENCE_V0_2_ENABLED=true`

```
POST /evidence/search
  -> load ExpansionConfig from env flags + rules JSON
  -> preprocess_evidence_search_request(payload, config)   [query expansion + root gating]
       -> on exception: warning appended, ORIGINAL query used, continue
  -> call baseline v1.5.10 handler with the (possibly expanded) query
       -> on exception: retry baseline handler with the ORIGINAL query, warning appended
  -> if response is a dict and WHO rerank enabled:
       rerank_who_results(response, original_query, expansion)
         -> on exception: warning appended, baseline WHO ordering kept
  -> if EVIDENCE_V0_2_DEBUG: attach diagnostics / query_original / query_effective
  -> return response (all baseline fields — source_status, figures, curriculum_results,
     html, warnings, etc. — untouched except for the warnings array and, when WHO rerank
     succeeds, the ordering/annotations of who_results)
```

## Why this satisfies the mission's fail-open requirement

Every v0_2 step (config load + query expansion, dispatch with expanded query, WHO
rerank) is wrapped in its own `try/except`. A failure at any stage:

- Appends a specific, greppable warning string (e.g.
  `v0_2_query_expansion_failed_using_baseline_query: ...`,
  `v0_2_expanded_query_dispatch_failed_retried_original_query: ...`,
  `v0_2_who_rerank_failed_baseline_ranking_used: ...`,
  `v0_2_unavailable_baseline_used: ...`).
- Falls back to the baseline result for that stage rather than raising or dropping
  a source. In particular, if the EXPANDED query itself causes the baseline dispatch
  to throw (e.g. malformed expansion text), the wrapper **retries with the original,
  unmodified query** before giving up — see `test_expanded_query_dispatch_failure_retries_original_query`
  in `tests/test_v0_2_fallback_behavior.py`.

Verified with unit tests that directly monkeypatch each failure point (`tests/test_v0_2_fallback_behavior.py`,
5 tests, all passing) — see `docs/V0_2_LOCAL_TEST_RESULTS_20260705.md`.

## What v0_2 does NOT touch

- `sources` list, `max_results`, `include_figures`, `max_figures`, `render_html`,
  `html_profile`, and all other request fields are passed through to the baseline
  handler unchanged (only `query` is ever conditionally rewritten, and only for
  dispatch — the caller's `original_query` is preserved for rerank/diagnostics).
- `figures`, `curriculum_results`, `html`, and `source_status` fields in the response
  are never mutated by the wrapper (verified in `tests/test_figure_url_preservation.py`,
  `tests/test_html_bundle_preservation.py`, `tests/test_source_status_contract.py`).
- Non-dict responses (e.g. a raw `Response` object for certain HTML bundle profiles)
  are returned untouched — the wrapper only touches `dict` responses.

## Root gating fix discovered and applied during integration

While wiring this up, a genuine bug was found in `evidence_search_reliability_v0_2/query_expansion.py`:
the `allow_standalone` escape hatch (meant to let single-allowed-root abbreviations like
`SSL`/`CRC`/`AIS`/`SCCIS`/`CMF` expand even with zero organ-context words in the query)
was checked only inside the `required_context_terms` branch, which is unreachable
because the earlier `root_allowed(...)` gate already rejects any query with zero
inferred roots first. Fixed by resolving `allow_standalone` before both gates (see
`docs/V0_2_1_RULE_CHANGELOG_20260705.md` for the diagnostic evidence and regression
check). All 27 pre-existing v0_2 unit tests still pass after the fix.
