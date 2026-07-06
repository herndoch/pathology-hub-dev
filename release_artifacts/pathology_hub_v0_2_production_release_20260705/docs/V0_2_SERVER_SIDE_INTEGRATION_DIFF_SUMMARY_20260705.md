# v0_2 Server-Side Integration — Diff Summary — 2026-07-05

## `backend/pathology_hub_v04_live_recovered/app.py`

- Lines 1–3202: byte-identical to `recovered_backend/v04_10_live_source/app.py` (the
  verified live 1.5.10 production source). **Zero modifications.**
- Lines 3203–3413 (211 new lines): the v0_2 server-side integration wrapper described in
  `docs/V0_2_SERVER_SIDE_INTEGRATION_DESIGN_20260705.md` — new `/health` and
  `/evidence/search` route registrations, feature-flag parsing, try/except-wrapped calls
  into `evidence_search_reliability_v0_2`.
- File grew from 3202 -> 3413 lines. Total diff: +211 / -0 relative to the recovered
  baseline (purely additive).

## `backend/evidence_search_reliability_v0_2/config.py`

```
 5 insertions, 0 deletions
```

Added `root_gating_enabled: bool = True` field to `ExpansionConfig` and a
`root_gating_enabled` parameter to `load_config()`, sourced from the
`EVIDENCE_ROOT_GATING_ENABLED` env var. Purely additive; default preserves prior
behavior (root gating always on) for any caller that doesn't pass the new parameter.

## `backend/evidence_search_reliability_v0_2/query_expansion.py`

```
26 insertions, 10 deletions (net +16)
```

Two changes:

1. Root-gating checks (`is_blocked_root`, `root_allowed`) now respect
   `config.root_gating_enabled` (gate can be fully disabled via env flag for
   diagnostics/testing; defaults to enabled).
2. **Bug fix:** moved `allow_standalone` resolution before the `root_allowed` gate.
   Previously, a rule with `allow_standalone: true` and a single `allowed_roots` entry
   could never actually take effect for a truly standalone query (zero organ-context
   words), because `root_allowed(inferred={}, allowed=[...])` always returns `False`
   for empty `inferred`, and that check ran BEFORE the standalone escape hatch was ever
   consulted. Fixed by inferring the single allowed root up front when
   `allow_standalone` is set, before both the `root_allowed` and
   `required_context_terms` gates run.

Regression safety: all 27 pre-existing unit tests in `tests/test_evidence_query_expansion_v0_2.py`,
`tests/test_evidence_v0_2_regression_gate.py`, `tests/test_evidence_root_gating_v0_2.py` still pass
after both changes. An offline replay against all 1008 cached v0_1/v0_2 benchmark queries
confirmed the fix changes the expansion decision for exactly the 5 abbreviations targeted
by the v0_2.1 rule changelog (`SSL`, `CRC`, `AIS`, `SCCIS`, `CMF`) plus the new `NOS`
title-boost rule, and zero other queries in the 1008-row set — see
`docs/V0_2_1_RULE_CHANGELOG_20260705.md`.

## `backend/query_expansion_rules_v0_2_1.json` (new file)

New rule file, not a modification of `backend/query_expansion_rules_v0_2.json` (kept
unmodified as the "as-audited" baseline). See `docs/V0_2_1_RULE_CHANGELOG_20260705.md`.

## Files copied verbatim into `backend/pathology_hub_v04_live_recovered/` for deploy packaging

- `evidence_search_reliability_v0_2/` (with the two fixes above)
- `query_expansion_rules_v0_2.json` and `query_expansion_rules_v0_2_1.json`
- `requirements.txt`, `Dockerfile` (from the recovered source tarball)
