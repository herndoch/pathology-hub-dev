# Current Master Spine Addendum — Pathology Hub v04.8, 2026-06-29

## Canonical architecture
Pathology Hub is a chat-first pathology assistant with separate workstreams:

- Evidence RAG
- Report-style RAG
- Gross template generation
- HTML/rendered teaching output
- Backend API
- Custom GPT frontend

Do not merge these workstreams into a single undocumented format. Workstream outputs must plug into the shared architecture and shared schemas.

## Live API canonical state

```text
Service: pathology-hub-v04
URL: https://pathology-hub-v04-vorn5q2kga-uc.a.run.app
Revision: pathology-hub-v04-00014-mbj
Version: 1.5.8-pathout-lecture-tags-v04
Endpoint: POST /evidence/search
Operation ID: searchEvidence
Authentication: X-API-Key from Secret Manager secret pathology-hub-api-key
```

## One Action only
The Custom GPT must use one external Action only:

```text
searchEvidence
POST /evidence/search
```

Do not add or expect separate `journalSearch`, `textbookSearch`, `pathoutSearch`, `whoSearch`, `lectureSearch`, or `videoSearch` Actions.

## Supported sources

```text
who
textbooks
journals
pathout
lectures
videos
```

Aliases accepted by the backend:
- `lecture`, `lectures`, `video`, `videos` route to lecture vector search.
- `pathology_outlines` routes to `pathout`.

## Source status summary

### WHO
- Upstream/passthrough source.
- Use for official terminology, definitions, essential/desirable criteria, and classification framing.
- Not locally vectorized by current audit.

### Textbooks
- Normalized/chunked/FTS indexed/vectorized.
- Primary-tag sidecar complete and API-exposed as of v04.8.
- Page-image and PDF page links are API-exposed where available.
- Tags are page-level primary tags inherited to chunks; useful for routing/boosting, not final diagnostic truth.

### Journals
- Upstream journal FTS plus local journal FAISS vector hybrid.
- Vector records: 103,830.
- API-exposed via v04.5+ and live in v04.8.

### PathOut
- AP-diagnostic clean pages scoped/tagged/vectorized offline.
- Vector records: 4,397.
- API-exposed as of v04.8.
- Metadata/tag quality remains rough in some records; many remain `__UNMAPPED__`.

### Lectures/videos
- STRICT_CYTO_v9 routed-only chunks tagged and vectorized.
- Vector records: 42,069.
- API-exposed as `lectures` and `videos` as of v04.8.
- Uncertain chunks held out.
- Known issue: `video_time_url` often null because upstream docstore lacks parsed start/end/video URL fields.

## Counts

```text
Textbook sources: 47
Textbook pages primary-tag joined: 27,836
Textbook chunks primary-tag inherited: 81,117
Textbook chunks unmapped or missing after repair: 26,957
Journal vector records: 103,830
PathOut AP vector records: 4,397
Lecture STRICT_CYTO_v9 vector records: 42,069
Public textbook figure map records loaded: 61,012
Textbook page-image inventory records loaded: 28,705
Source locator registry records loaded: 280
```

## Project rule
Do not claim a source is indexed, vectorized, tagged, or API-exposed unless health output, manifest, audit, or source docs prove it.
