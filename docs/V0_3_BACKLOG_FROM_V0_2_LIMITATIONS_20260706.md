# v0_3 Backlog — Derived from v0_2 Accepted Limitations — 2026-07-06

Two tickets, both derived from limitations explicitly reviewed and accepted as
known/acceptable by Charlie during the v0_2 production release approval (see
`docs/V0_2_GO_NO_GO_DECISION_20260705.md` and
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/DECISIONS_LOG_20260705_v0_2_ADDENDUM.md`,
decision #7). **Neither ticket is scoped for immediate work.** Per the mission's
explicit instruction, no v0_3 code changes are made in this task.

---

## PH-v0_3-01 — BREAST_002 / NOS retrieval-pool limitation

### Problem

The WHO source does not surface the correct entity for the query `"Invasive ductal
carcinoma, NOS"` (entity BREAST_002, exact_name query type), in either
`include_figures` state, even after a v0_2.1 attempted fix.

### Evidence from the v0_2 benchmark (cited from our own miss register)

From `docs/V0_2_REMAINING_MISS_REGISTER_20260705.md`, row 1:

> BREAST_002 — Invasive ductal carcinoma, NOS | "Invasive ductal carcinoma, NOS"
> (exact_name) | who | 2 (both `include_figures` states) | **Attempted, not
> resolved.** Added a WHO title-boost alias rule (`NOS` -> "no special type"/"NST")
> in v0_2.1; did not flip this to a hit. Reranking cannot promote a candidate that
> was never retrieved in the top-10 pool for this exact query text.

Confirmed live in the Phase 7 staging benchmark (`docs/V0_2_STAGING_BENCHMARK_RESULTS_20260705.md`):
this remained one of the 12 final misses out of 1008, with the `NOS` title-boost
alias rule (`backend/query_expansion_rules_v0_2_1.json`) present and active but not
changing the outcome.

### Suspected root cause

The rule added in v0_2.1 uses `expansion_mode: "title_boost_only"`, which affects
**post-retrieval reranking** of whatever WHO already returned, but does not change
the query text dispatched to the WHO upstream retrieval. If the correct WHO record
(likely titled with 5th-edition terminology, e.g. "invasive carcinoma of no special
type (NST)") is not among the top-N candidates the upstream retrieval returns for
the literal query `"Invasive ductal carcinoma, NOS"`, no amount of reranking within
that candidate set can surface it. This is a **retrieval/pool-size problem, not a
ranking-order problem** — not yet proven with direct evidence (no direct probe of
the WHO upstream's raw candidate pool for this exact query was performed in the
v0_2 release), so this remains a suspicion pending investigation, not a confirmed
diagnosis.

### Proposed investigation (investigation only — no code changes)

1. Probe the WHO upstream retrieval directly for the literal query, with a larger
   result window (e.g. `max_results=25-50` instead of the benchmark's 10), and check
   whether the correct WHO record appears anywhere in that larger window. If yes,
   this confirms a pool-size issue (fixable by requesting a larger internal
   candidate pool before reranking). If no, this may instead indicate the correct
   WHO 5th-edition record uses different terminology entirely and needs an
   `append_query`/`replace_short_token`-style expansion mode change (which DOES alter
   dispatched query text) rather than `title_boost_only`.
2. Directly inspect the actual WHO Breast chapter content (via
   `gs://pathology-hub-0/WHO/WHO_HTML/BREAST/` or the WHO JSON processed source) to
   confirm the exact canonical title/terminology used for this entity, rather than
   assuming "no special type"/"NST" is correct.
3. If a query-text-rewriting fix is warranted, change the `NOS` rule's
   `expansion_mode` from `title_boost_only` to `append_query` (append "no special
   type" directly into the dispatched query) — but this is a HIGHER-RISK change than
   `title_boost_only` since it alters what is actually searched, and requires its own
   full 1008-row regression pass (not just this one entity) before being considered
   safe.

### Files likely touched (future work, not touched now)

- `backend/query_expansion_rules_v0_2_1.json` (or a new `v0_2_2` rules file, to keep
  `v0_2_1` as an audited, deployed baseline)
- Possibly `backend/evidence_search_reliability_v0_2/query_expansion.py` if a new
  expansion mode or pool-size parameter is needed
- No changes anticipated to `backend/pathology_hub_v04_live_recovered/app.py` itself
  unless the WHO upstream call's `max_results`/pool parameter needs to be
  independently configurable from the client-facing `max_results`

### Tests/benchmark needed

- A targeted, non-benchmark WHO upstream probe script (new, small) to directly
  inspect the raw candidate pool for this query before any rule change.
- If a rule change is made: full 1008-row live benchmark rerun (not just this
  entity) to confirm no regression, per the same anti-overfitting discipline used in
  v0_2.1.
- Existing `tests/test_evidence_query_expansion_v0_2.py` suite must still pass.

### Acceptance criteria

- BREAST_002 (both `include_figures` states) becomes a confirmed hit in a live
  benchmark rerun, AND the full 1008-row benchmark shows zero new misses among the
  other 1006 rows (i.e. net improvement, not a lateral trade).

### Stop condition

- If the investigation step (1) shows the correct WHO record is NOT retrievable even
  with a much larger candidate pool (i.e. it may not exist in the corpus at all, or
  the true terminology differs substantially from "NOS"/"NST"), stop and reclassify
  this as a corpus/terminology gap rather than a retrieval-pool bug, and do not force
  a synthetic fix.
- Maximum 2 rule-tuning iterations before requiring a full architecture review, per
  the same discipline applied throughout the v0_2 release.

### Risk of overfitting

**Medium.** This is a single-entity fix. Any query-text-rewriting change (e.g.
switching to `append_query` mode) must be verified against the full 1008-row
benchmark, not just BREAST_002, since `append_query` mode is more invasive than
`title_boost_only` and could shift ranking for unrelated breast-root queries that
happen to contain "NOS" in other contexts (e.g. a hypothetical future entity using
"NOS" outside the breast/ductal/invasive context guard already in place).

---

## PH-v0_3-02 — GU_005 WHO ranking / token-overlap limitation

### Problem

The WHO source ranks two incorrect entities ("Villous adenoma", "Tubular adenoma")
above the correct entity ("Nephrogenic adenoma") for the
`entity_plus_morphology`-type query `"Nephrogenic adenoma tubular architecture"`.

### Evidence from the v0_2 benchmark (cited from our own miss register)

From `docs/V0_2_REMAINING_MISS_REGISTER_20260705.md`, row 3:

> GU_005 — Nephrogenic adenoma | "Nephrogenic adenoma tubular architecture"
> (entity_plus_morphology) | who | 2 | **True ranking limitation, not attempted.**
> Top WHO hits are lexically similar but wrong entities ("Villous
> adenoma"/"Tubular adenoma") because the morphology descriptor "tubular
> architecture" (auto-generated by the benchmark's query builder from the entity
> CSV) shares tokens with those wrong entities. Not an abbreviation-rule issue; a
> general WHO title-boost heuristic change was judged too broad/risky to attempt on
> a single-entity basis in this session (mission explicitly warns against
> overfitting to individual misses).

Confirmed live in the Phase 7 staging benchmark: this remained one of the 12 final
misses out of 1008, and this is not an abbreviation/query-expansion issue — no
governed rule applies to this query at all.

### Suspected root cause

`who_ranking.py`'s `_title_boost_score` function scores candidate hits primarily by
raw token overlap (`overlap * 0.15`, capped at 1.5) plus fixed bonuses for exact
substring containment. For this query, the tokens `{"nephrogenic", "adenoma",
"tubular", "architecture"}` overlap more with "Tubular adenoma" (shares "tubular",
"adenoma") and "Villous adenoma" (shares "adenoma") than the current scoring
mechanism sufficiently penalizes, relative to the smaller, more specific overlap with
the actually-correct "Nephrogenic adenoma" (shares "nephrogenic", "adenoma" — same
count of shared tokens, 2, as "tubular adenoma", so the current heuristic cannot
distinguish them by token overlap alone).

### Proposed investigation (investigation only — no code changes)

1. Confirm this hypothesis directly: fetch the actual WHO candidate results for this
   query (`max_results=10+`) and inspect their raw scores and computed
   `who_title_boost_v0_2` boost values to see exactly how close the scoring margin
   is between the correct and incorrect entities.
2. Design a targeted `who_ranking.py` improvement: e.g., increase the weight given to
   an exact full first-word match ("Nephrogenic" as the entity's defining/rare term)
   relative to generic shared terms ("adenoma" appears in dozens of WHO entities and
   should carry less discriminating weight than a rare, specific term). This likely
   requires an IDF-like (inverse document frequency) weighting scheme rather than
   flat per-token overlap scoring — a bigger architectural change than a simple
   constant tweak.
3. Explicitly test the proposed scoring change against **all** WHO-source queries in
   the 1008-row benchmark (not just GU_005), since a general ranking-weight change
   has broad blast radius across every WHO query, unlike the narrowly-scoped
   abbreviation rules used in v0_2.1.

### Files likely touched (future work, not touched now)

- `backend/evidence_search_reliability_v0_2/who_ranking.py` (the `_title_boost_score`
  function specifically)
- Possibly a new corpus-wide term-frequency reference table if an IDF-style approach
  is adopted (new data file, not yet designed)
- `tests/` — new unit tests for the ranking function directly (currently no
  dedicated `who_ranking.py` unit test exists beyond what's exercised indirectly via
  `tests/test_evidence_query_expansion_v0_2.py`)

### Tests/benchmark needed

- New, dedicated unit tests for `_title_boost_score` / `apply_who_title_boost`
  covering: exact-name queries, entity_plus_morphology queries, and at least one
  adversarial case with high generic-token overlap (like GU_005) to prevent
  regressing this exact scenario in the future.
- Full 1008-row live benchmark rerun required before considering any ranking-weight
  change safe — this is explicitly a WHO-wide change, not entity-scoped.

### Acceptance criteria

- GU_005 (both `include_figures` states) becomes a confirmed hit, AND the full
  1008-row benchmark shows zero net regression among the other WHO-source queries
  that currently pass (this is the highest-risk criterion in this backlog, since WHO
  ranking changes are the most likely to cause a regression elsewhere).

### Stop condition

- If a targeted `who_ranking.py` change cannot be found that fixes GU_005 without
  causing at least one new miss elsewhere in the WHO-source portion of the 1008-row
  benchmark, **do not deploy the change** — document it as a fundamental limitation
  of token-overlap-based reranking and consider it out of scope until a more
  substantial ranking architecture (e.g. actual semantic embedding-based rerank for
  WHO, not just title-token overlap) is evaluated as a separate, larger initiative.
- Maximum 2 tuning iterations before requiring architecture review, consistent with
  the discipline used throughout the v0_2 release.

### Risk of overfitting

**High.** This is explicitly a general ranking-function change, not a scoped rule
addition. Unlike PH-v0_3-01 (which can be scoped to a `NOS`-specific, breast-context-gated
rule), any fix here necessarily changes scoring behavior for every WHO query, making
it the single highest-risk item in this backlog. The mission's anti-overfitting
instruction applies most strongly here: **do not tune this against GU_005 alone.**
