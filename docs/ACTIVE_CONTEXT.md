# Active Context

Last updated: 2026-07-08

## Current task (completed)

Built the textbook figure image quality-flag sidecar and browser UI update
described in `docs/RUNBOOK_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md`, per
the runbook's final/approved (2026-07-08) tier table (used as-is, not
re-derived).

### Why (this task)

The full-population image dimension audit (52,540/52,540 textbook images,
see prior task below) actually completed after the stratified-8000 fallback
was already summarized. Full results:
`06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_full_v0_1.json`
— 9.16% overall flag rate. Re-analysis against the full population (not the
sample) found `gi_atlas` fig02/03/04 as the worst offenders (81.3%, 73.5%,
47.5% flag rates), in addition to the previously confirmed
`cyto_comprehensive_part_one/two` fig01 (2592x235 fixed crop) and `gu_practical`
fig01/02 (7x7 degenerate) patterns. Full evidence and tier rationale:
`docs/PROPOSAL_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md`.

### What was built

- `scripts/build_textbook_figure_image_quality_flags_v0_1.py` — new,
  sidecar-only, read-only script. Reads
  `flagged_figure_images_full_v0_1.csv` (4,835 flagged rows), tags each row
  `suppress_render` (Tier A `source_id`/`fig_slot` pairs from the runbook) or
  `warn_render` (every other flagged row), and writes:
  - `outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`
    (4,835 rows: `record_id`, `chunk_id`, `source_id`, `fig_slot`, `width`,
    `height`, `aspect_ratio`, `flags`, `tier`).
  - `06_audits/curriculum_provenance_links/v0_1/figure_image_quality_flags_audit_v0_1.json`
    (`schema_version`, `created_at`, `input_paths`, `output_paths`, `counts`
    with `total_rows`/`tier_a_count`/`tier_b_count`/per-`source_id` breakdown,
    `known_limitations`).
  - Counts: **3,382 Tier A (`suppress_render`)**, **1,453 Tier B
    (`warn_render`)**, 4,835 total. Matches the runbook's Tier A pair list
    exactly (11 `(source_id, fig_slot)` pairs).
- `tools/curriculum_provenance_browser/app.py` — loads the quality-flags
  JSONL read-only at startup (cached in-memory dict keyed by `record_id`, no
  SQLite schema change), attaches a `quality_flag: {tier, flags, width,
  height} | null` field to every `/api/search` row and to
  `/api/records/{id}`. Added an optional `quality` search filter
  (`all`/`suppressed`/`flagged`/`clean`) applied in-memory after the existing
  SQL query.
- `tools/curriculum_provenance_browser/static/index.html` — `suppress_render`
  rows show "Known extraction defect — image suppressed" plus flag reasons
  and parsed dimensions instead of the image locator line (other locator
  fields still render normally); `warn_render` rows get a visible "⚠ suspect
  dimensions" badge with reasons and width x height. Added a `quality`
  filter dropdown and a dedicated "Image quality" results column, plus a
  matching quality-flag block in the record detail view.
- `tests/test_curriculum_provenance_browser.py` — added a small fixture
  quality-flags JSONL (one Tier A, one Tier B row, keyed to two real
  `record_id`s sharing a rare `approved_tag` in the sqlite index) and two new
  tests: one asserting `/api/records/{id}` returns
  `quality_flag.tier == "suppress_render"` for the Tier A id and
  `"warn_render"` for the Tier B id (plus `null` for an unflagged record);
  one exercising the `quality` search filter's `all`/`suppressed`/`flagged`/
  `clean` values and its 422 on an invalid value. Full suite: **6/6 tests
  pass** (`tools/curriculum_provenance_browser/.venv/bin/python -m
  unittest tests.test_curriculum_provenance_browser -v`).

### Deviation from the runbook (documented, not a scope change)

The runbook says the `quality` filter is "applied in-memory after the
existing SQL query." Implemented literally with the SQL query's
`LIMIT`/`OFFSET` kept as-is, a `quality != "all"` filter would silently
under-fill or double-count pages (filtering a fixed-size page can shrink it
below `limit`, and the reported `total` would still be the pre-filter SQL
count). To keep `total` and pagination correct when a `quality` filter other
than `all` is requested, the SQL `WHERE` clause is unchanged, but
`LIMIT`/`OFFSET` are dropped from SQL and applied in Python after the
in-memory quality filter instead (the default `quality=all` path is
byte-for-byte the original SQL-paginated behavior, unchanged). No SQL filter
clause was added for `quality` itself, consistent with the runbook's
constraint.

### Immediate next step

Run the browser locally and visually confirm one Tier A and one Tier B
example:

```bash
tools/curriculum_provenance_browser/scripts/run_local.sh
# open http://127.0.0.1:8765/, filter "Image quality flag" = Suppressed/​Flagged
```

Do not start on the fig01-fallback logic change in
`scripts/build_curriculum_source_locator_repairs_v0_1.py` (separate,
not-yet-approved change) or re-run the network audit — both remain out of
scope per the runbook's stop condition.

## Prior task (completed)

Completed the textbook figure/page image dimension audit runbook using the
large fallback sample pass (`--sample-size 8000`) after the full 52,540-image
run proved too slow for the current session.

### Why

Manual spot-checks in the curriculum provenance browser found that textbook
figure image locators are frequently wrong or degenerate:

- 71.6% of textbook rows with an image point at the first figure slot
  (`fig01`) on the page; 95.2% of *page text chunks* with an image use this
  `fig01` fallback (from `scripts/build_curriculum_source_locator_repairs_v0_1.py`,
  which assigns the first figure seen on a page to any text chunk missing
  its own image).
- A 300-image random sample flagged ~10% as extreme aspect ratio, strip
  shaped, or near-zero pixel dimensions.
- 40/40 random `fig01` images from `cyto_comprehensive_part_one` /
  `cyto_comprehensive_part_two` were exactly `2592x235` pixels regardless of
  page or figure content — a fixed crop-region bug, not natural variation.
  `hn_gnepp` showed a similar fixed signature near `1313x118`.
- This matches a prior caveat already on record in
  `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/00_MASTER_HANDOFF_FOR_CODEX.md`
  about reported header/footer crop junk.

### Tooling already built and validated (small scale only)

`scripts/audit_textbook_figure_image_dimensions_v0_1.py` — read-only,
sidecar-only. Parses JPEG/PNG/JP2 headers from a byte-range fetch (no PIL, no
full-image download) and flags extreme aspect ratio / strip shape / tiny
images. Validated on a 300-image random sample: 0 fetch errors, 0 unparsed
headers (added JP2/`.jpx` support after the first test run caught a gap).
Not yet run at full scale (52,540 unique textbook image locators).

### What was run

- Exact full command was started twice:
  `python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py --sample-size 0 --concurrency 24 --run-tag full`
- In the current environment the full run did not produce outputs within a
  reasonable interval, so the runbook fallback was used:
  `python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py --sample-size 8000 --concurrency 24 --run-tag stratified8000`
- A tiny diagnostic run also completed successfully:
  `python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py --sample-size 10 --concurrency 4 --run-tag diag10`

### Immediate next step (for Codex or next agent)

Use the audit outputs below to decide whether a separate, explicitly-approved
repair pass should suppress known-bad `(source_id, fig_slot)` patterns or
prefer different textbook image assignment logic for `page_text_chunk` rows.
Do not write repairs in the same session unless the user explicitly reopens
that scope.

## Prior task

Local curriculum provenance browser for querying and debugging the repaired source locator SQLite index.

## Current state

- GCP user auth is active for `herndon.charlie@gmail.com`.
- ADC credentials were refreshed and saved under the local gcloud config.
- Active project is `pathology-annotation-project`.
- Secret Manager metadata has been verified for several external API credentials; values were not read.
- Prior memory indicates PathOut page-level records include `source_url` and figure URLs.
- Prior memory indicates accepted tags were root-grouped into a sidecar JSON.
- `scripts/audit_curriculum_provenance_links_v0_1.py` has been created and rerun with source-family-specific locator logic.
- The v0.1 audit processed 159,771 curriculum records.
- Source-family counts were: `abpath` 6,105; `textbooks` 98,151; `lectures` 53,378; `pathout` 1,752; `who` 385.
- ABPath is now classified as ontology/tag-origin metadata, not a source corpus requiring source links.
- A full record-level provenance sidecar now exists at `06_audits/curriculum_provenance_links/v0_1/record_provenance_sidecar_v0_1.jsonl`.
- Full lecture and textbook vector docstores were copied locally to `data/curriculum_provenance_repair_v0_1/` for repair joins.
- `scripts/build_curriculum_source_locator_repairs_v0_1.py` produced a repair sidecar and repaired provenance sidecar.
- Repair pass changed 71,420 records: 42,738 textbook rows and 28,682 lecture rows.
- Final locator completeness counts after repair: `abpath` 6,105 complete; `pathout` 1,752 complete; `who` 385 complete; `lectures` 49,537 complete and 3,841 partial; `textbooks` 69,034 complete and 29,117 partial.
- Remaining gaps after repair: lecture timestamp recovery for 3,841 rows, textbook page image or figure image recovery for 27,181 rows, and textbook raw PDF URI recovery for 2,338 rows.
- `scripts/build_curriculum_source_locator_index_v0_1.py` produced a derived rich SQLite provenance index with 159,771 `provenance_records` rows.
- `tools/curriculum_provenance_browser/` provides a local read-only FastAPI search/debug UI over the SQLite index.

## Immediate next step

Run the local browser and use it to evaluate query quality, partial provenance visibility, and source locator rendering before any downstream API or GPT integration.

```bash
tools/curriculum_provenance_browser/scripts/run_local.sh
# open http://127.0.0.1:8765/
```

## Intended output directory

`tools/curriculum_provenance_browser/`

## Expected local outputs

- `tools/curriculum_provenance_browser/app.py`
- `tools/curriculum_provenance_browser/static/index.html`
- `tools/curriculum_provenance_browser/scripts/run_local.sh`
- `tests/test_curriculum_provenance_browser.py`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_stratified8000_v0_1.json`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/flagged_figure_images_stratified8000_v0_1.csv`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_diag10_v0_1.json`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/flagged_figure_images_diag10_v0_1.csv`

## Boundaries

- Codex and Cursor may read from, write to, upload to, and mutate GCS when they decide that is needed for the assigned task.
- For planned upload paths, prefer an audit JSON with `schema_version`, input paths, output paths, counts, and known limitations.
- No overwrite of original normalized records.
- No modification of raw chunks, vector docstores, FAISS indexes, or prior curriculum map outputs.
- The browser is read-only and must not mutate the SQLite index from the UI.
- Sidecar-only repair maps are allowed after audit evidence supports them.

## Deferred ideas (not started, for later discussion)

- External literature/knowledge API integration is a **separate future
  workstream**, not yet started and not part of the current provenance/image
  audit work. Secret Manager already has credentials for `OncoKB`, `Elsevier`,
  `SpringerOpen`, `SpringerMeta`, and `NCBI` (see `docs/SECRET_REFERENCES.md`),
  but none of these are called anywhere in current backend/frontend code today.
- The existing `journals` source in `/evidence/search` is served from a local
  FAISS vector index built ahead of time, not a live pass-through to any of
  the five external APIs above.
- If this workstream is picked up later: keep it separate from Evidence RAG /
  curriculum provenance work per `AGENTS.md`'s "keep workstreams separate"
  rule, and note that `OncoKB` (genomic variant interpretation) is a
  different kind of API than the four literature/journal APIs.

## Coordination notes for agents

- Update this file when changing the current task, blocker, touched files, outputs, or next step.
- If another agent has changed files unexpectedly, stop and ask the user how to proceed.
- Keep generated large data under `outputs/`, `data/`, or `06_audits/` as appropriate; do not commit large generated corpora unless explicitly requested.
