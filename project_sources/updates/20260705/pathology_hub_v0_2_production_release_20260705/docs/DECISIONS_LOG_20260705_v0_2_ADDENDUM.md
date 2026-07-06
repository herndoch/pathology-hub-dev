# Decisions Log Addendum — 2026-07-05/06 — Evidence Search Reliability v0_2 Production Release

Chronological, dated. Each decision cites the doc where its rationale/evidence is
recorded in full (repo root `docs/` unless noted).

1. **(2026-07-05) Integrate v0_2 into the recovered live source, not the stale local
   1.5.7 copy.** Rationale: the stale copy is missing three shipped feature
   generations (PathOut/lecture tags, Curriculum Map v0.2, HTML bundle) and a
   textbook-vector-search resilience fix already present in live production; patching
   v0_2 onto it would have been a feature regression. See
   `docs/WHY_STALE_1_5_7_MUST_NOT_BE_PATCHED_DIRECTLY.md`.

2. **(2026-07-05) v0_2 integration must be additive-only and fail-open.** Every v0_2
   stage (query expansion, dispatch with expanded query, WHO rerank) wrapped in its
   own try/except; on any failure, falls back to the baseline result with an explicit
   warning. No source may become unavailable solely because v0_2 fails. See
   `docs/V0_2_SERVER_SIDE_INTEGRATION_DESIGN_20260705.md`.

3. **(2026-07-05) Fix the `allow_standalone` ordering bug in
   `query_expansion.py` rather than leaving the 5 affected abbreviations
   (SSL/CRC/AIS/SCCIS/CMF) permanently un-expandable.** Verified via the full
   pre-existing 27-test suite (still 27/27 passing) plus an offline regression replay
   confirming the fix changes expansion decisions for exactly the 24 intended rows
   and zero others. See `docs/V0_2_1_RULE_CHANGELOG_20260705.md`.

4. **(2026-07-05) Do NOT attempt further fixes for `CIS` standalone
   (GU_003), Bullous pemphigoid (SKIN_001), or the GU_005 ranking issue in this
   release**, to avoid overfitting narrow single-entity heuristics against the
   mission's explicit anti-overfitting instruction. `CIS` has 3 plausible anatomic
   roots (genuine ambiguity); Bullous pemphigoid is a true, permanent WHO
   Classification of Tumours corpus gap (not a tumour entity); GU_005's issue is a
   general ranking-weight limitation requiring its own broader regression pass. See
   `docs/V0_2_29_MISS_DIAGNOSTIC_RESULTS_20260705.md` and
   `docs/V0_2_REMAINING_MISS_REGISTER_20260705.md`.

5. **(2026-07-05) Go/No-Go decision: GO**, based on all 7 mission-defined
   production-authorization gates being met (production snapshot exists, rollback
   command recorded, staging deploy succeeded, staging smoke tests pass, benchmark
   gates pass with documented non-regressive remaining misses, no secret exposure
   required, no destructive canonical GCS operation required). See
   `docs/V0_2_GO_NO_GO_DECISION_20260705.md`.

6. **(2026-07-06) Charlie explicitly approved Phase 8 (production deploy) and Phase 9
   (gradual traffic rollout)**, equivalent to typing
   `APPROVE_PRODUCTION_DEPLOY_EVIDENCE_SEARCH_V0_2`, via a structured decision in his
   own message, after reviewing the Go/No-Go decision (996/1008, 12 documented
   non-regressive misses, all 7 gates met).

7. **(2026-07-06) Charlie explicitly accepted BREAST_002/NOS and GU_005 as
   known/acceptable limitations for this release**, instructing that both be tracked
   as v0_3 follow-up tickets rather than attempted further in this session. This
   decision is recorded verbatim in the same approval message as decision 6, and
   reflected in `docs/V0_2_GO_NO_GO_DECISION_20260705.md` and the release handoff doc.

8. **(2026-07-06) Deploy production with `--no-traffic --tag=v0-2-candidate` first,
   verify in isolation, then shift traffic gradually (10% -> 50% -> 100%)** rather
   than a direct cutover, per Charlie's explicit Phase 8/9 instructions. See
   `docs/PRODUCTION_DEPLOY_LOG_V0_2_20260705.md` and
   `docs/PRODUCTION_TRAFFIC_SHIFT_LOG_V0_2_20260705.md`.

9. **(2026-07-06) Mandatory pre-flight re-verification performed immediately before
   any production write action**, per Charlie's explicit instruction not to skip it
   even though time had passed since the Go/No-Go decision. Result: rollback target
   unchanged, production env vars byte-identical to the Phase 0 snapshot,
   `min-instances` found to be 0/unset (documented, not previously known). See
   `docs/PRODUCTION_PREFLIGHT_REVERIFICATION_20260706.md`.

10. **(2026-07-06) Apply `min-instances=1` to production as a follow-up, scaling-config-only
    change** (no app code deploy, no traffic shift), applying the same fix already
    proven safe on staging, per Charlie's explicit follow-up approval. Verified this
    did not create a new revision and did not change the serving image or traffic
    split. See `docs/PRODUCTION_MIN_INSTANCES_FIX_20260705.md`.

11. **(2026-07-06) Do not merge `production-v0-2-recovery-release-20260705` into
    `master` autonomously.** A read-only merge-readiness review was produced
    (`docs/MERGE_READINESS_V0_2_20260705.md`) confirming the branch is a clean
    fast-forward candidate, but the actual `git merge`/`git push` commands were
    deliberately NOT executed — merge remains pending Charlie's explicit manual
    action.
