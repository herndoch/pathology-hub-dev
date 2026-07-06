# Why the Stale 1.5.7 `app.py` Must Not Be Patched Directly

**Short answer:** because it is missing three generations of already-shipped production
features (PathOut/lecture tags, Curriculum Map v0.2, HTML bundle) and a resilience fix
that current production already has independently of v0_2. Patching v0_2 onto it and
deploying would be a **feature regression disguised as a reliability upgrade**.

## Concrete failure scenarios this would cause, if deployed to staging or production

1. **Phase 6 curriculum test would fail.** `docs/NEXT_10_ENGINEERING_TICKETS_20260705.md`
   and the mission's Phase 6 checklist require a curriculum behavior test. A service
   built from 1.5.7 has no `source="curriculum"` dispatch at all — the test would fail
   with an unknown-source error, not a data problem, misleading triage toward "curriculum
   corpus missing" when the real cause is "wrong base version."

2. **Phase 6 HTML bundle test would fail identically.** `render_html`/`html_profile`
   are not fields on 1.5.7's `EvidenceSearchRequest` model at all — a request setting
   `render_html: true` would be silently ignored (extra Pydantic fields are ignored by
   default) rather than erroring, which is worse: it would look like the HTML bundle
   endpoint "worked" but returned a normal JSON search response instead of HTML.

3. **PathOut/lecture governed-tag smoke tests would regress.** The 1.5.7 copy predates
   the 1.5.8 PathOut/lecture tag dispatch entirely, so `pathout`/`lectures`/`videos`
   sources would not be exposed the same way (if at all), causing a false "v0_2 broke
   PathOut" signal during Phase 6 smoke testing when the real cause is the base version.

4. **Silent reintroduction of a fixed textbook failure mode.** The recovered 1.5.10
   source wraps `vector_search_pool(...)` in a `try/except` that falls back to
   FTS-only textbook search with an explicit warning when the vector index has a
   transient problem. The 1.5.7 copy has no such guard. Three of this session's own
   Phase 4 miss diagnostics (`BREAST_001`, `BST_005` — textbooks; `HN_001` — journals)
   show `source_unavailable` failures in the ORIGINAL v0_1/v0_2 client-side benchmark
   that ran against production; deploying a v0_2 build on top of 1.5.7 would make this
   class of failure worse, not better, at the exact moment the mission is trying to
   *reduce* misses.

5. **Version string would be misleading.** A 1.5.7-based build reporting a v0_2-staging
   version suffix would make `/health` claim a lineage that never actually shipped
   PathOut tags, curriculum, or HTML bundle — violating the workspace rule "never claim
   a source is indexed/vectorized/tagged/API-exposed unless a health check, manifest,
   audit, or project source proves it," because the health response itself would be
   internally inconsistent with the actual code running.

## What this session did instead

Integrated v0_2 into `recovered_backend/v04_10_live_source/app.py` (the exact,
digest-verified live production source), not the stale 1.5.7 copy. See
`docs/LIVE_BACKEND_VS_LOCAL_1_5_7_RECONCILIATION_REPORT.md` for the diff, and
`docs/V0_2_SERVER_SIDE_INTEGRATION_DESIGN_20260705.md` for how the wrapper was added
without touching any of the recovered baseline code.

The stale `backend/pathology_hub_v04_curriculum/app.py` is left in the repo, untouched,
purely as a historical/structural reference — it must not be treated as deployable or
production-equivalent going forward.
