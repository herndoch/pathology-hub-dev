# Live Backend (1.5.10) vs. Local Stale Copy (1.5.7) — Reconciliation Report

**Source of truth for this diff:** `diff recovered_backend/v04_8_cloudbuild_source/app.py recovered_backend/v04_10_live_source/app.py` and structural comparison against `backend/pathology_hub_v04_curriculum/app.py` (the repo's stale 1.5.7 copy).

## Headline finding

The stale repo copy (`backend/pathology_hub_v04_curriculum/app.py`, 2263 lines, `APP_VERSION = "1.5.7-page-images-v04"`) stops **three version blocks before** the verified live source (`recovered_backend/v04_10_live_source/app.py`, 3202 lines, terminal version `1.5.10-html-bundle`). The file is append-only (each version block removes and re-registers `/health` and `/evidence/search`), so the missing 939 lines are not cosmetic — they are entire feature generations.

## What is missing from the stale 1.5.7 copy

| Version block | Lines (approx, in recovered source) | Feature | Present in stale 1.5.7 copy? |
|---|---|---|---|
| 1.5.8-pathout-lecture-tags-v04 | 1684–2262 | PathOut + lecture governed-tag dispatch, `pathout_endpoint`, lecture STRICT_CYTO_v9 routed retrieval | **No** |
| 1.5.9-curriculum-map-v02 | 2284–2711 | Curriculum Map v0.2 as `source="curriculum"` on the same `searchEvidence` action; forbidden-tag filtering | **No** |
| 1.5.10-html-bundle | 2712–3202 | `render_html`/`html_profile` HTML bundle generation (teaching_page/gallery/evidence_packet) | **No** |
| (resilience fix, embedded in 1.5.10 textbook block) | ~602–669 | `try/except` around `vector_search_pool` with graceful FTS-only fallback + explicit warning when textbook vector search fails | **No** — the stale copy's textbook path has no fallback; a vector search exception there propagates as a hard error rather than degrading gracefully |

## Additional field-level diffs

- `EvidenceSearchRequest` model in the recovered 1.5.10 source has 6 additional fields not present in 1.5.7: `render_html`, `html_profile`, `html_title`, `target_figure_count`, `html_include_toc`, `html_include_source_sections`.
- Imports: recovered source adds `csv, html` to the top-level import line (used by HTML bundle rendering and curriculum CSV loading) — absent from 1.5.7.

## Why this matters for v0_2 integration

1. **Wrong hook point risk:** If v0_2 had been patched into the stale 1.5.7 `/evidence/search` handler (as an earlier prior-session artifact, `backend/pathology_hub_v04_curriculum/evidence_search_v0_2_patch.py`, appears to have explored), the resulting service would **not** have PathOut/lecture tag dispatch, curriculum source, HTML bundles, or the textbook vector-search resilience fix — i.e. it would look like a "v0_2-enabled" service that is actually missing three generations of production features and would fail Phase 6/7 smoke tests (curriculum, HTML bundle, PathOut tag).
2. **Silent regression risk:** The missing textbook resilience fix is the most dangerous omission — patching v0_2 onto 1.5.7 would reintroduce a textbook-vector-search hard-failure mode that the *actual* current production has already fixed independently of v0_2.
3. **Correct approach taken in this session:** v0_2 was integrated into `recovered_backend/v04_10_live_source/app.py` (copied into `backend/pathology_hub_v04_live_recovered/app.py`), preserving 100% of the 1.5.8/1.5.9/1.5.10 feature generations, with the v0_2 wrapper added strictly on top as new, additive, feature-flagged code (see `docs/V0_2_SERVER_SIDE_INTEGRATION_DESIGN_20260705.md`).

See also `docs/WHY_STALE_1_5_7_MUST_NOT_BE_PATCHED_DIRECTLY.md` for the concrete failure scenarios this would have caused.
