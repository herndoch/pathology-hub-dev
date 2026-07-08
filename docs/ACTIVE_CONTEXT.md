# Active Context

Last updated: 2026-07-08

## Current task

Handoff to Codex: run the full-scale textbook figure/page image dimension
audit described in `docs/RUNBOOK_TEXTBOOK_FIGURE_IMAGE_DIMENSION_AUDIT.md`.

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

### Immediate next step (for Codex or next agent)

Follow `docs/RUNBOOK_TEXTBOOK_FIGURE_IMAGE_DIMENSION_AUDIT.md` to run the
full-scale (or large stratified) audit, then report flag rates and worst
offending `(source_id, fig_slot)` combinations. Do not build a repair pass
in the same session — that requires explicit user approval per the
runbook's stop condition.

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

## Boundaries

- Codex and Cursor may read from, write to, upload to, and mutate GCS when they decide that is needed for the assigned task.
- For planned upload paths, prefer an audit JSON with `schema_version`, input paths, output paths, counts, and known limitations.
- No overwrite of original normalized records.
- No modification of raw chunks, vector docstores, FAISS indexes, or prior curriculum map outputs.
- The browser is read-only and must not mutate the SQLite index from the UI.
- Sidecar-only repair maps are allowed after audit evidence supports them.

## Coordination notes for agents

- Update this file when changing the current task, blocker, touched files, outputs, or next step.
- If another agent has changed files unexpectedly, stop and ask the user how to proceed.
- Keep generated large data under `outputs/`, `data/`, or `06_audits/` as appropriate; do not commit large generated corpora unless explicitly requested.
