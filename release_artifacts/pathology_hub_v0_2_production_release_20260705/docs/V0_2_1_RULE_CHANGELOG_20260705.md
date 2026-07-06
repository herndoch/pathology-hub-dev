# v0_2.1 Rule Changelog — 2026-07-05

New file: `backend/query_expansion_rules_v0_2_1.json` (the original
`backend/query_expansion_rules_v0_2.json` is left unmodified as the audited baseline).

## Changes

### 1. `allow_standalone: true` added to 5 existing rules

| Abbreviation | allowed_roots | Miss rows targeted |
|---|---|---|
| `SSL` | `["GI"]` | GI_001, 4 rows (who x2, textbooks x2) |
| `CRC` | `["GI"]` | GI_002, 4 rows (who x2, pathout x2) |
| `AIS` | `["GYN"]` | GYN_004, 2 rows (pathout x2) |
| `SCCIS` | `["Skin"]` | SKIN_003, 2 rows (who x2) |
| `CMF` | `["BST"]` | BST_004, 2 rows (pathout x2) |

Each of these has exactly one `allowed_root`, so inferring that root when the query is
a bare abbreviation with zero other organ-context words carries low ambiguity risk.
`CIS` was deliberately **not** given `allow_standalone` because it has three allowed
roots (`GU`, `GYN`, `Skin`) — a bare "CIS" query is genuinely ambiguous between bladder,
cervical, and skin carcinoma-in-situ, and guessing wrong risks a `wrong_root_preferred`
regression that is worse than the current conservative miss.

**This change required a companion bug fix** in `evidence_search_reliability_v0_2/query_expansion.py`
(see `docs/V0_2_SERVER_SIDE_INTEGRATION_DIFF_SUMMARY_20260705.md`) — without it,
`allow_standalone` was unreachable code.

### 2. New rule: `NOS` title-boost alias (Breast-context-gated)

```json
{
  "abbreviation": "NOS",
  "expansions": ["no special type", "NST", "not otherwise specified"],
  "allowed_roots": ["Breast"],
  "required_context_terms": ["breast", "ductal", "invasive", "mammary"],
  "blocked_roots": [],
  "expansion_mode": "title_boost_only",
  "allow_standalone": false
}
```

`title_boost_only` mode never rewrites the dispatched query text — it only feeds the
WHO reranker (`who_ranking.py`) an extra term to match against candidate titles. Gated
by `required_context_terms` (breast/ductal/invasive/mammary must already be present in
the query) so it cannot fire for unrelated non-breast uses of "NOS" (a generic pathology
qualifier used across nearly every organ system). `allow_standalone: false` is
deliberate — "NOS" alone, with no organ context, is far too generic to safely infer
Breast.

## Regression safety check (offline, zero live API calls)

Ran `expand_query()` from both the old (`query_expansion_rules_v0_2.json`) and new
(`query_expansion_rules_v0_2_1.json`) rule sets against all 1008 cached
(query, source) pairs from the prior live benchmark run, and diffed the resulting
`effective_query` / `expansions_applied` decision for every row.

**Result: exactly 24 rows changed (6 distinct query/source families x ~4 rows each:
SSL, CRC, AIS, SCCIS, CMF, NOS-on-BREAST_002), and zero unintended changes among the
other ~984 rows.** This confirms the fix is scoped precisely to its intended targets
and does not alter expansion behavior for any of the other 33 benchmark entities.

Command used (reproducible): see the inline script embedded in this session's
transcript / re-derivable via:

```bash
python3 - <<'PY'
import json, sys
sys.path.insert(0, "backend")
from evidence_search_reliability_v0_2.config import load_config
from evidence_search_reliability_v0_2.query_expansion import expand_query

raw = json.load(open("06_audits/evidence_retrieval_writable/benchmark_v0_2/benchmark_v0_2_results_raw.json"))
cfg_old = load_config(rules_path="backend/query_expansion_rules_v0_2.json")
cfg_new = load_config(rules_path="backend/query_expansion_rules_v0_2_1.json")
seen = set()
changed = 0
for run in raw["runs"]:
    key = (run["query"], run["source"])
    if key in seen: continue
    seen.add(key)
    old = expand_query(run["query"], sources=[run["source"]], config=cfg_old)
    new = expand_query(run["query"], sources=[run["source"]], config=cfg_new)
    if old.effective_query != new.effective_query:
        changed += 1
print("distinct (query,source) pairs changed:", changed, "/", len(seen))
PY
```

## Known residual risk

Governed abbreviation rules operate on substring/token matches within the query text.
Real-world GPT-generated queries could combine these abbreviations with unrelated
context in ways not present in the 1008-row benchmark set. The existing `blocked_roots`
mechanism and the conservative choice to leave `CIS` gated are the primary mitigations;
the Phase 7 staging benchmark (live, full 1008-row run) is the actual verification of
whether this rule set improves the miss count without introducing new
`wrong_root_preferred`/`wrong_entity_preferred` regressions among the other ~979 passes.
