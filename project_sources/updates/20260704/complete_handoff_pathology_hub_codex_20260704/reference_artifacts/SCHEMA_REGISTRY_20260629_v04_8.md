# Schema Registry Addendum — 2026-06-29 v04.8

## evidence_search_response.v1.5.8
Returned by `POST /evidence/search`.

Important top-level fields:
- `query`
- `source_status`
- `search_mode`
- `who_results`
- `journal_results`
- `pathout_results`
- `textbook_results`
- `lecture_results`
- `video_results`
- `figures`
- `warnings`

## textbook_primary_tag_map.v1
Page-level primary-tag map generated from completed textbook tagging jobs.

Fields:
- `source_family = textbooks`
- `page_key`
- `page_id`
- `source_id`
- `page`
- `primary_tag`
- `tag_status`
- `tag_basis`
- `tag_notes`
- `job_zip`

## textbook_primary_tagged_pages_v1.jsonl
Textbook page objects enriched with:
- `primary_tag`
- `primary_tag_status`
- `primary_tag_basis`

## textbook_primary_tagged_chunks_v1.jsonl
Textbook chunks enriched by inheriting page-level primary tags.

Fields added:
- `primary_tag`
- `primary_tag_status`
- `primary_tag_basis`
- `primary_tag_join_key`

## pathout_ap_diagnostic_vector_manifest.v1
Offline PathOut AP-diagnostic vector manifest.

Expected values:
- `vectorized = true`
- `api_exposed = false` in manifest, because API exposure is tracked by live service health.
- Live v04.8 health exposes it with `pathout_ap_api_exposed = true`.

## lecture_primary_tag_map.STRICT_CYTO_v9
Map from lecture chunk IDs to primary tags from completed STRICT_CYTO_v9 jobs.

Fields:
- `chunk_id`
- `video_id`
- `primary_tag`
- `tag_status`
- `tag_basis`
- `tag_notes`

## lecture_timecoded_vector_manifest.STRICT_CYTO_v9
Offline lecture vector manifest.

Expected values:
- `record_count = 42069`
- `embedding_model = text-embedding-3-small`
- `embedding_dim = 1536`
- `vectorized = true`
- `api_exposed = false` in manifest; live health exposes API status.

## Controlled tags
The deduplicated controlled tag set from `Tags.zip` contains 6,105 real full-path tags, or 6,106 if adding `__UNMAPPED__`.
