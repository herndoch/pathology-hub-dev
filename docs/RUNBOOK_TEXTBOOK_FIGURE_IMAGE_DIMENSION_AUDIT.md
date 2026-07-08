# Textbook Figure/Page Image Dimension Audit Runbook

## Goal

Determine how often textbook figure images in the curriculum provenance index
are actually header/footer-crop junk or otherwise degenerate (wrong aspect
ratio, near-empty pixel content) rather than real figure panels, and whether
the pattern concentrates in specific books, chunk types, or figure slots.

This is a read-only measurement pass. It does not repair or reassign any
image locator. Repairs are a separate, later, explicitly-approved step.

## Why this exists

Manual spot-checks (Cursor session, 2026-07-08) found:

- 71.6% of textbook rows with an attached image point at the first figure
  slot on the page (`fig01`), including 95.2% of *page text chunks* (as
  opposed to caption chunks), because the repair fallback in
  `scripts/build_curriculum_source_locator_repairs_v0_1.py` assigns the first
  figure seen on a `(source_id, page)` to any text chunk missing its own
  image.
- In a 300-image random sample, ~10% of fetched images had extreme aspect
  ratios, wide/tall "strip" shapes, or near-zero pixel dimensions.
- A targeted check of 40 random `fig01` images from
  `cyto_comprehensive_part_one` / `cyto_comprehensive_part_two` found **all
  40 were exactly `2592x235` pixels** — the same fixed crop rectangle
  regardless of page or figure content. `hn_gnepp` showed a similar fixed
  signature near `1313x118`.
- This matches a prior caveat already on record in
  `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/00_MASTER_HANDOFF_FOR_CODEX.md`:
  "The user has reported header/footer crop junk, so deeper
  image-dimension/content cleanup may still be needed."

## Scope

Read-only against:
- `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite`
  (local, read-only connection only)
- Public HTTP image bytes at `https://storage.googleapis.com/pathology_hub/...`
  (byte-range GET of the first ~256KB per image; no full-corpus download)

## Non-goals / boundaries

- Codex and Cursor may use GCS if needed, but this task only requires public
  HTTP reads of already-public image URLs. No GCS write/mutate calls are
  needed for the audit itself.
- Do not modify `curriculum_source_locator_index_v0_1.sqlite`, any vector
  docstore, FAISS index, or normalized record.
- Do not modify `curriculum_record_provenance_sidecar_repaired_v0_1.jsonl`.
- Do not reassign, delete, or "fix" any `image_path`/`image_url` value as
  part of this audit. That is a separate repair step gated on this audit's
  results plus explicit user approval.
- Do not upload audit outputs to GCS unless the user explicitly asks.

## Script (already built and validated at small scale)

`scripts/audit_textbook_figure_image_dimensions_v0_1.py`

- Reads unique `(image_url or image_path)` locators for `source_family='textbooks'`
  from the SQLite index (read-only connection, `mode=ro`).
- Fetches a byte-range prefix of each image and parses real pixel dimensions
  from JPEG, PNG, and JP2/JPEG2000 (`.jpx`) headers — no PIL dependency, no
  full-image download.
- Classifies each image: `extreme_aspect_ratio`, `wide_strip_header_footer_suspect`,
  `tall_strip_suspect`, `tiny_image`, or `fetch_error` / `unparsed_header`.
- Cross-tabs flags by `chunk_kind` (`caption_chunk` vs `page_text_chunk`) and
  `fig_slot` (`fig01`, `fig02`, ...).
- Writes a local audit JSON (`schema_version`, `input_paths`, `output_paths`,
  `counts`, `known_limitations`) and a flagged-rows CSV. No other files are
  written or modified.

Already validated locally on a 300-image random sample (0 fetch errors, 0
unparsed headers after adding JP2 support) — see
`06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_test300_v0_1.json`
for the reference small-scale run.

## Full-scale run

There are 52,540 unique textbook image locators in the current index. Run:

```bash
python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py \
  --sample-size 0 \
  --concurrency 24 \
  --run-tag full
```

Expected runtime: roughly 45-75 minutes at the tested throughput
(~17-20 images/sec at concurrency 20; adjust `--concurrency` down if GCS
throttles or errors climb).

If a full run is too slow or noisy, an intermediate option is a larger
stratified sample, e.g.:

```bash
python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py \
  --sample-size 8000 \
  --concurrency 24 \
  --run-tag stratified8000
```

## Outputs

- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_<run_tag>_v0_1.json`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/flagged_figure_images_<run_tag>_v0_1.csv`

## What to check in the results

1. Overall flag rate (`any_flag_rate_pct`) and how it splits between
   `caption_chunk` and `page_text_chunk` in `by_chunk_kind`.
2. Whether specific `source_id` values (books) or `fig_slot` values
   concentrate the flags — especially any book/slot combination showing a
   single recurring exact `(width, height)` pair, which indicates a fixed
   crop-region bug rather than natural figure variation. Group the flagged
   CSV by `source_id, fig_slot, width, height` to find these.
3. Whether `tiny_image` rows correspond to very small file sizes (near-empty
   or placeholder extractions) versus real (if small) figures.

## Repair rule

Do not build a repair pass in the same run as the audit. If the audit
confirms systematic fixed-crop or degenerate-image patterns, propose a
sidecar repair plan (e.g., suppress/flag known-bad `(source_id, fig_slot)`
combinations, or prefer `page_images` over first-figure fallback for
`page_text_chunk` rows) and get explicit user approval before writing any
repair sidecar.

## Stop condition

Stop after producing the audit JSON/CSV and a written summary of findings
(flag rates, worst offending books/slots, and whether the fixed-crop pattern
generalizes beyond `cyto_comprehensive_part_one/two` and `hn_gnepp`). Do not
proceed to repairs, index changes, or GCS uploads without explicit user
approval.
