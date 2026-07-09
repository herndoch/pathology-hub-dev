# Textbook Figure Image Quality Flag Sidecar + Browser UI Runbook

Status: **approved by user 2026-07-08.** Tier A and Tier B classifications
below are final. Build against them as-is.

This supersedes the "proposal only" status in
`docs/PROPOSAL_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md`. That file is
the evidence/rationale record; this file is the build spec.

## Goal

Build a read-only, sidecar-only quality-flag layer over the textbook figure
image locators already in
`outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite`,
and surface it in `tools/curriculum_provenance_browser/`, so known-bad
header/footer-crop and degenerate images stop being shown as reliable
figures, without deleting or reassigning any locator.

## Inputs (already produced, do not regenerate)

- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_full_v0_1.json`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/flagged_figure_images_full_v0_1.csv`
  (4,835 flagged rows out of 52,540 unique textbook images; columns include
  `record_id, chunk_id, chunk_kind, source_id, pdf_page, approved_tag,
  fig_slot, url, width, height, aspect_ratio, fetch_status, flags`)

## Final tier assignment (approved, do not re-derive)

### Tier A — `suppress_render` for matching flagged rows

Apply to any row in the flagged CSV whose `(source_id, fig_slot)` is one of:

```
cyto_comprehensive_part_one, fig01
cyto_comprehensive_part_two, fig01
gu_practical, fig01
gu_practical, fig02
gu_practical, fig03
hn_gnepp, fig02
hn_gnepp, fig03
hn_gnepp, fig04
gi_atlas, fig02
gi_atlas, fig03
gi_atlas, fig04
```

Only the specific flagged rows within these pairs get `suppress_render` —
not every image in that slot. Non-flagged rows in the same
`(source_id, fig_slot)` are untouched and keep rendering normally.

### Tier B — `warn_render` for all other flagged rows

Every row in the flagged CSV whose `(source_id, fig_slot)` is NOT in the
Tier A list above gets `warn_render`: still shown, with a visible badge
listing the flag reason(s) (`extreme_aspect_ratio`,
`wide_strip_header_footer_suspect`, `tall_strip_suspect`, `tiny_image`,
`fetch_error`) and the parsed `width`/`height`.

### Everything not in the flagged CSV

No entry in the sidecar. Renders exactly as it does today, no change.

## Build steps

### 1. Quality-flag sidecar script

New script: `scripts/build_textbook_figure_image_quality_flags_v0_1.py`

- Read `flagged_figure_images_full_v0_1.csv`.
- For each row, assign `tier` per the Tier A list above (exact
  `(source_id, fig_slot)` match) else `warn_render`.
- Write:
  - `outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`
    — one JSON object per flagged row: `record_id`, `chunk_id`, `source_id`,
    `fig_slot`, `width`, `height`, `aspect_ratio`, `flags` (list, from the
    CSV `flags` column split on `;`), `tier`.
  - Paired audit JSON at
    `06_audits/curriculum_provenance_links/v0_1/figure_image_quality_flags_audit_v0_1.json`
    with `schema_version`, `created_at`, `input_paths`, `output_paths`,
    `counts` (total rows, tier_a count, tier_b count, per-source_id
    breakdown), `known_limitations`.
- Sidecar-only: do not open
  `curriculum_source_locator_index_v0_1.sqlite` or
  `curriculum_record_provenance_sidecar_repaired_v0_1.jsonl` in write mode.
  Do not touch any GCS object. Do not reassign any `image_path`/`image_url`
  anywhere.

### 2. Browser UI update (`tools/curriculum_provenance_browser/`)

`app.py`:
- On startup, load the new quality-flags JSONL into an in-memory dict keyed
  by `record_id` (read-only file read, not a DB connection).
- In `_enrich_row`/`_build_locator_summary` (or equivalent), attach
  `quality_flag: {tier, flags, width, height} | null` to each returned row
  and to the single-record detail endpoint.
- Add an optional search filter param, e.g. `quality` with values
  `all | suppressed | flagged | clean`, applied in-memory after the SQL
  query (do not change the SQLite query itself beyond existing filters).

`static/index.html`:
- If a row's `quality_flag.tier == "suppress_render"`: do not render the
  image/locator preview as reliable; show "Known extraction defect — image
  suppressed" plus the flag reasons and parsed dimensions instead of the
  normal locator preview for that row's image portion. Non-image locator
  fields (page, source PDF, etc.) still show normally.
- If `tier == "warn_render"`: show existing locator info plus a visible
  "⚠ suspect dimensions" badge with flag reasons and `width x height`.
- Add a toggle/filter control for the new `quality` param (`all` /
  `suppressed` / `flagged` / `clean`).
- Detail view: show the same quality-flag block.

### 3. Tests

Extend `tests/test_curriculum_provenance_browser.py`:
- Add a test that stubs/loads a small fixture quality-flags JSONL and
  asserts a Tier A record_id comes back with `quality_flag.tier ==
  "suppress_render"` and a Tier B one with `warn_render`.
- Add a test for the new `quality` filter parameter.

### 4. Update `docs/ACTIVE_CONTEXT.md`

Record what was built, output paths, and next step (e.g. "run the browser
locally and visually confirm a Tier A and Tier B example").

## Non-goals (unchanged from the proposal)

- Do not reassign, delete, or regenerate any `image_path`/`image_url`.
- Do not touch GCS objects.
- Do not modify
  `scripts/build_curriculum_source_locator_repairs_v0_1.py` or its
  fig01-fallback logic — that is a separate, larger, not-yet-approved
  change.
- Do not modify `curriculum_source_locator_index_v0_1.sqlite` or
  `curriculum_record_provenance_sidecar_repaired_v0_1.jsonl`.

## Permissions for this task

Full local read/write permission is granted for this task: creating the new
script, the new sidecar JSONL, the new audit JSON, and editing
`tools/curriculum_provenance_browser/app.py`,
`tools/curriculum_provenance_browser/static/index.html`,
`tests/test_curriculum_provenance_browser.py`, and `docs/ACTIVE_CONTEXT.md`.
No GCS write/mutate access is needed for this task and none should be used.

## Stop condition

Stop after the sidecar, audit JSON, browser UI update, and passing tests are
in place, plus the `docs/ACTIVE_CONTEXT.md` update. Do not start on the
separate fig01-fallback logic change or re-run the network audit — both are
out of scope for this runbook.
