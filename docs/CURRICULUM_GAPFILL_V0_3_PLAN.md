# Curriculum Gap Fill v0.3 Plan

## Scope and constraints
- Workstream: Evidence/Lesson/Research RAG.
- Target: build reviewable gap-fill sidecars for ABPath coverage in
  - `lecture` (STRICT_CYTO_v9)
  - `textbook`
  - order: **lectures first**, then textbooks.
- No source mutation:
  - no overwrite of raw normalized records,
  - no FAISS/vector rebuild,
  - no Cloud Run deploy,
  - no GPT Builder or API schema edits.
- Forbidden/generated tags are never ontology nodes.

## Source inventory reviewed
### Governance docs/handoffs used
- `AGENTS.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/00_MASTER_HANDOFF_FOR_CODEX.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/01_LIVE_STATE_AND_PROOF.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/03_GCS_PATHS_AND_OBJECTS.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/06_TAG_POLICY_AND_GOVERNANCE.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/07_CURRICULUM_MAPPING_STRATEGY_AND_V11.md`
- `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/reference_artifacts/pathology_hub_abpath_source_tags.zip`

### Local source inputs
| Path | Source | Rows | Size | Notes |
| --- | --- | ---: | ---: | --- |
| `data/curriculum_map_v0_2/abpath_source_tags.jsonl` | ABPath gold ontology | 6,105 | 0.95 MB | `primary_tag` field is source truth |
| `data/curriculum_map_v0_2/lecture_primary_tag_map_STRICT_CYTO_v9.jsonl` | Lecture tags map | 42,069 | 56.2 MB | controlled + generated lecture tags |
| `data/curriculum_map_v0_2/lecture_timecoded_tagged_chunks_ROUTED_ONLY_STRICT_CYTO_v9.jsonl` | Lecture chunks | 42,069 | 107.4 MB | rich chunk text + transcript metadata |
| `data/curriculum_map_v0_2/textbook_primary_tagged_chunks_v1.jsonl` | Textbook chunks | 81,117 | 467.6 MB | includes `candidate_tags`, `primary_tag`, `text` |
| `data/curriculum_map_v0_2/pathout_tagged_pages_AP_DIAGNOSTIC_v1.jsonl` | PathOut reference only | 4,397 | 106.2 MB | not in gap-fill output scope |
| `data/curriculum_map_v0_2/who_processed/*.json` | WHO map context | 19 files / 131,731 records | 14.0 MB | optional governance cross-check only |

### GCS live input references (size-checked)
| URI | Size | Status |
| --- | --- | --- |
| `gs://pathology_hub/02_normalized/textbooks/lean/tags/textbook_primary_tagged_chunks_v1.jsonl` | expected for live textbook tag source | ~same controlled content family |
| `gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl` | 104.38 MiB | exists |
| `gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl` | 220.22 MiB | exists |
| `gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json` | 10.06 KiB | exists |
| `gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json` | 13.97 MiB (19 files) | exists |

### Current v0.2 baseline (for comparison)
- Inputs from `data/curriculum_map_v0_2/*`, outputs in `release_artifacts/curriculum_map_v0_2/*`.
- `curriculum_nodes_v0_2.csv` 6,105 nodes / 454,687 bytes.
- `review_queue_v0_2.csv` 4,245 rows.
- `rejected_tags_v0_2.csv` 36,284 rows.
- `acceptance_summary_v0_2.json`: 137,293 visible curriculum records; 0 forbidden visible tags.

## Proposed output files (new sidecars only)
- `docs/` scope outputs:
  - `docs/CURRICULUM_GAPFILL_V0_3_PLAN.md` (this file)
- Candidate/approved sidecars (required, new files):
  - `lecture_abpath_gapfill_candidates_v0_3.jsonl`
  - `lecture_abpath_gapfill_approved_v0_3.jsonl`
  - `textbook_abpath_gapfill_candidates_v0_3.jsonl`
  - `textbook_abpath_gapfill_approved_v0_3.jsonl`

## Proposed schema
Per-line JSON schema (for both candidate/approved files unless otherwise filtered):
- `schema_version` (string, fixed `curriculum_gapfill_v0_3`)
- `source_family` (string: `lectures` or `textbooks`)
- `chunk_id` / `record_id` (string)
- `source_id` (string)
- `abpath_tag` (string)
- `root` (string)
- `matched_query` (string)
- `matched_terms` (string[])
- `score` (float, 0..1 or 0..100)
- `confidence` (enum: `high`,`medium`,`low`)
- `method` (enum: `exact_phrase`,`term_cluster`,`abpath_synonym`,`title_match`,`fts_rank`)
- `review_status` (enum: `approved`,`review_queue`,`reject_hard`)
- `text_excerpt` (string)
- `original_existing_tag` (string|null)
- `reason` (string)

## Search and scoring plan
1. Build local SQLite+FTS5 index per family from source chunks using columns: `source_id`, `chunk_id`, `source_tag`, `title`, `text` (`text` fields include lecture `transcript_text`/`title`; textbook `text` + captions).
2. Expand ABPath tags into candidate queries:
   - `tag path` normalized (`::` -> space),
   - leaf label only,
   - alias set from curated synonyms (e.g., hyphen/space variants, common abbreviations).
3. Scoring:
   - `exact_phrase` match on normalized phrase in title/transcript/text: base +0.40
   - `term_cluster` match (>=2 terms in same window): base +0.35
   - FTS rank normalized: base +0.25
   - root-consistency bonus (candidate root present in source lineage fields): +0.10
4. confidence thresholds:
   - `high`: score >= 0.90 (or exact phrase + strong root), auto-write to approved file.
   - `medium`: 0.70–0.89, send to candidates with `review_queue`.
   - `low`: <0.70, reject/hide.
5. Review control: reject any candidate where:
   - original tag contains forbidden artifact patterns,
   - match is rootless/unsupported,
   - term expansion creates generated-only tag not in ABPath set.

## Risk controls
- Use only ABPath tags as approved ontology; WHO/PathOut behavior remains unchanged in v0.3 scope.
- Keep full audit trail in each row `reason` + matched terms + source fields.
- Do not promote anything to live or write back into governed metadata until manual approval pass passes.
- Do not touch vector/normalized source files or GCS without new write-up and explicit approval.

## Commands to run (planned, not executed)
- Local bootstrap and checks:
  - `python3 scripts/curriculum_gapfill_v0_3.py --source-family lectures --input-dir data/curriculum_map_v0_2 --output-dir outputs/curriculum_gapfill_v0_3 --sample-size 0 --max-output 5000`
  - `python3 scripts/curriculum_gapfill_v0_3.py --source-family textbooks --input-dir data/curriculum_map_v0_2 --output-dir outputs/curriculum_gapfill_v0_3 --sample-size 0 --max-output 5000`
- Optional SQL index creation sanity:
  - `sqlite3 outputs/curriculum_gapfill_v0_3/gapfill_v0_3.sqlite < scripts/gapfill_v0_3_schema.sql`

## Estimated data sizes
- Input ingest footprint: ~752 MB local (`data/curriculum_map_v0_2`).
- Candidate outputs (estimated initial): lectures ~2–8% of rows; textbooks ~1–5% of rows.
- SQLite FTS index expected to be ~1.3–2.0x input text bytes for lecture/textbook chunks.

## Recommendation
Start with lectures first for v0.3:
1) STRICT_CYTO_v9 has already-governed structures and source-family sequencing, which reduces false-positive risk,
2) smaller/faster validation loop than textbook corpus,
3) it directly improves the highest-noise source for search quality before scaling to textbook chunks.
