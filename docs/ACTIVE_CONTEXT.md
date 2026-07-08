# Active Context

Last updated: 2026-07-08

## Current task

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
