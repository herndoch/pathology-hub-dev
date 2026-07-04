# Workstream Status — 2026-06-29 v04.8

## Evidence RAG
### Textbooks
- Status: API-exposed hybrid FTS + FAISS vector with primary-tag sidecar and page images.
- Current API: `sources=["textbooks"]`.
- Primary tags: page-level sidecar inherited to chunks.
- GCS sidecar: `gs://pathology_hub/02_normalized/textbooks/lean/tags/textbook_primary_tagged_chunks_v1.jsonl`.

### Journals
- Status: API-exposed upstream FTS + local FAISS vector hybrid.
- Current API: `sources=["journals"]`.
- Records: 103,830.

### PathOut
- Status: API-exposed upstream PathOut plus local AP-diagnostic FAISS vector.
- Current API: `sources=["pathout"]`.
- Records: 4,397.
- Caveat: metadata and primary tags require future cleanup.

### WHO
- Status: upstream/passthrough.
- Current API: `sources=["who"]`.
- Not locally vectorized by current audit.

### Lectures/videos
- Status: API-exposed local STRICT_CYTO_v9 routed-only FAISS vector.
- Current API: `sources=["lectures"]` or `sources=["videos"]`.
- Records: 42,069.
- Caveat: `video_time_url` usually null until v04.9.

## Backend API
- Current service: `pathology-hub-v04`.
- Current revision: `pathology-hub-v04-00014-mbj`.
- Current version: `1.5.8-pathout-lecture-tags-v04`.
- One Action only: `searchEvidence`.

## Custom GPT frontend
- Must update OpenAPI schema to v1.5.8.
- Must replace older GPT instructions with v1.5.8 core instructions.
- Must use staged sequential retrieval for complex teaching/profile questions.

## HTML/rendering
- Use returned JSON fields.
- Prefer `page_image_url`, `figure_url`, `image_url`, `source_page_url`, and eventually `video_time_url`.
- Do not invent or derive URLs that are not returned by the API.

## Not completed / next work
1. v04.9 lecture metadata/time parsing patch.
2. PathOut metadata/tag cleanup.
3. Optional section-level textbook tags beyond page-level sidecar.
4. Regression suite across sources.
