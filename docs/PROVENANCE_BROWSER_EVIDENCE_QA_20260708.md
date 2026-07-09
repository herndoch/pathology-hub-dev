# Provenance Browser + Evidence Search QA

Date: 2026-07-08

## Scope

Read-only QA pass over the local curriculum provenance browser and live
`/evidence/search` endpoint. No GCS writes, no SQLite/sidecar mutation, and no
fig01-fallback changes were made.

## Provenance Browser

Local browser:

- URL: `http://127.0.0.1:8765/`
- Health: `ok=true`
- SQLite: `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite`
- Quality flags sidecar loaded from:
  `outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`
- Browser is read-only per `/api/health`.

API filter checks:

- Default: `GET /api/search?limit=5` returned `total=159771` and partial/default records.
- Quality suppressed: `GET /api/search?quality=suppressed&limit=5` returned `total=3382`.
- Quality flagged: `GET /api/search?quality=flagged&limit=5` returned `total=4835`.
- Root BST: `GET /api/search?root=BST&limit=5` returned `total=18258`.
- Source family textbooks: `GET /api/search?source_family=textbooks&limit=5` returned `total=98151`.
- Approved tag substring: `GET /api/search?approved_tag=BST::Bone&limit=5` returned `total=8087`.

Fixture record IDs:

- Suppressed Tier A:
  `textbooks:tbchunk:cyto_comprehensive_part_two:cyto_comprehensive_part_two_p0489_fig001_caption`
  - `source_id=cyto_comprehensive_part_two`
  - `quality_flag.tier=suppress_render`
  - `flags=["extreme_aspect_ratio"]`
  - dimensions `2592x235`
- Suppressed Tier A:
  `gapfill_v0_4:textbooks:tbchunk:hn_gnepp:hn_gnepp_p0794_fig003_caption:BST::Soft_Tissue::Vascular::Benign::Papillary_Endothelial_Hyperplasia`
  - `source_id=hn_gnepp`
  - `quality_flag.tier=suppress_render`
  - flags include `extreme_aspect_ratio`, `wide_strip_header_footer_suspect`, `tiny_image`
  - dimensions `1313x118`
- Flagged Tier B:
  `textbooks:tbchunk:bst_horvai:bst_horvai_p0149_fig001_caption`
  - `source_id=bst_horvai`
  - `quality_flag.tier=warn_render`
  - `flags=["extreme_aspect_ratio"]`
  - dimensions `1724x235`

UI notes:

- The Windows browser was opened to `http://127.0.0.1:8765/`.
- The API backing the detail panel returns the expected `quality_flag` payload
  for both a suppressed row and a flagged row.
- Expected user-facing behavior is potentially non-obvious: default search
  does not focus quality-flag rows. Users must set `Image quality flag` to
  `Suppressed` or `Flagged` to see suppress/warn examples reliably.
- Suppressed rows should show the red suppressed badge and avoid rendering the
  bad image locator as an image; flagged rows should show the warning badge.

Test run:

- `tools/curriculum_provenance_browser/.venv/bin/python -m unittest tests.test_curriculum_provenance_browser -v`
  started but hung after printing `test_health ...`.
- Diagnostic rerun reached `after setup` and then timed out on
  `TestClient.get('/api/health')`.
- System `python3 -m unittest ...` cannot run the suite because the system
  Python environment is missing `fastapi`.
- Live local server `/api/health` and `/api/search` endpoints worked, so the
  blocker appears isolated to the in-process FastAPI/Starlette `TestClient`
  path in this environment.

## Evidence Search

Endpoint:

- `POST https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/evidence/search`
- API key was not present in `HUB_API` or `PATHOLOGY_HUB_API_KEY`; it was
  fetched from Secret Manager inside the process and was never printed or
  persisted.
- Response schema is source-specific arrays, not one generic `results` list:
  `textbook_results`, `pathout_results`, `who_results`, `lecture_results`,
  `video_results`, etc.

Query results:

- `{"query":"tubular adenoma colon","sources":["textbooks"],"max_results":5}`
  - `source_status.textbooks=ok`
  - `textbook_results=5`
  - Strong: top hits are GI neoplastic textbook pages/figures for tubular
    adenoma, including Figures 4.18, 4.19, 4.20, and 4.23.
  - Figure/page URLs are page image URLs under
    `pathology-hub-0/_asset_library/textbooks/.../page_images/...`, not the
    suppressed Tier A figure-image families checked in the provenance sidecar.
- `{"query":"LCIS breast","sources":["textbooks","pathout","who"],"max_results":5}`
  - `source_status.textbooks=ok`, `pathout=ok`, `who=ok`
  - `textbook_results=5`, `pathout_results=5`, `who_results=5`
  - Strong: textbook hits are Breast Biopsy / Breast Atlas LCIS pages; PathOut
    hits include classic LCIS, invasive lobular carcinoma classic, and
    pleomorphic LCIS.
- `{"query":"branchial cleft cyst","sources":["lectures"],"max_results":5}`
  - `source_status.lectures=ok`, `videos=ok`
  - `lecture_results=5`, `video_results=5`
  - Strong: top hits are all from `Benign Cystic Neck Mass (Case 01)` and
    include `Branchial_Cleft_Cyst` tags. Note that results duplicate across
    `lecture_results` and `video_results`.

Figure quality comparison:

- The evidence textbook queries returned page-image URLs rather than the known
  suppressed Tier A figure-image patterns from `cyto_comprehensive`,
  `gu_practical`, `gi_atlas`, or `hn_gnepp`.
- No new figure-quality repair was attempted.

## Recommendation

Keep the provenance debug UI separate from evidence search for now. It is doing
the right job as a record-level locator/quality debugger, while evidence search
is a retrieval endpoint with source-specific result contracts. Bridge later by
adding record/source locator cross-links from evidence results into the
provenance browser, rather than merging the UIs now.
