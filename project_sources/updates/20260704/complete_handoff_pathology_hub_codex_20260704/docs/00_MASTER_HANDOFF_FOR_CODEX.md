# Master Handoff for Codex — Pathology Hub Tag Governance and Curriculum Mapping

Generated: 2026-07-04T18:53:19+00:00

## Workstream name

Evidence/Lesson/Research RAG — tag governance, curriculum mapping, source metadata cleanup, and future tag-aware backend runtime.

This workstream is separate from report-style RAG, gross template generation, rendered HTML output, and Custom GPT UI polish.

## Canonical architecture reminders

- Keep one external GPT Action: `searchEvidence` / `POST /evidence/search`.
- Current live API service: `pathology-hub-v04`.
- Current base URL: `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app`.
- Current live response schema still identifies as `evidence_search_response.v1.5.8` and health `pathology_hub_health.v1.5.8`.
- New tag-aware fields/search modes are design/draft until backend patch + health + regression prove them live.

## Why this handoff exists

The project initially tried to make all records tag-bearing. That produced noisy generated ontology tags from weak-context lecture/textbook chunks. The user clarified that the highest-value goal is curriculum mapping, not maximal tag coverage.

Final governance policy from this conversation:

1. ABPath tags are gold/source-truth.
2. WHO processed JSON rows are tag-bearing source rows; WHO tags should map to ABPath where fuzzy score is high.
3. PathOut tags are generally useful and should be auto-approved as local curriculum tags unless obviously junk/root-broken.
4. Lecture/textbook generated tags must not create curriculum ontology nodes. Weak-context chunks should map to approved tags or inherit the nearest meaningful preceding tag in sequence.
5. If there is no approved tag and no valid inheritance context, a record should be governed-untagged and hidden from tag browsing/curriculum maps.
6. Junk figure derivatives should not be shown in retrieval/figures; raw PDFs/videos are never deleted.

## Current live/proven state

### Governed cleanup v10.5

Promoted with `PROMOTION_MODE = backup_replace_live`; Cloud Run restart was requested. The first notebook proof failed because it read the wrong Colab secret. The user then ran a proof cell that preferred `HUB_API` and sent it as HTTP header `X-API-Key`.

User-reported final proof:

```text
API key loaded: True length: 47
API key fingerprint: f1e4ad2e
HEALTH 200
['lectures'] status 200 forbidden 0
['who', 'textbooks', 'pathout', 'journals'] status 200 forbidden 0
['textbooks', 'pathout'] status 200 forbidden 0
API PROOF PASSED: all searches returned 200 and no forbidden primary tags.
GCS audit path: gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json
```

v10.5 uploaded ZIP summary before the key fix:

```json
{
  "promotion_mode": "backup_replace_live",
  "promotion_performed": true,
  "figure_filter_counts": {"total": 49526, "kept": 49525, "excluded": 1},
  "metadata_scan_counts": {
    "textbooks": {"total": 79320, "primary_tag_mapped": 79320, "primary_tag_governed_mapped": 79320, "unique_primary_tags": 2597},
    "pathout": {"total": 4397, "primary_tag_mapped": 4397, "primary_tag_governed_mapped": 4397, "unique_primary_tags": 4048},
    "lectures": {"total": 42069, "primary_tag_mapped": 42069, "primary_tag_governed_mapped": 42069, "unique_primary_tags": 1647}
  }
}
```

### Important caveats

- v10.5 proves standard search surfaces did not return forbidden primary-tag patterns in three representative authenticated tests. It does not prove a fully tag-aware browse API is live.
- Figure cleanup is still conservative. v10.5 summary excluded 1 of 49,526 served public figure-map records. The user has reported header/footer crop junk, so deeper image-dimension/content cleanup may still be needed.
- `HUB_API` is the working Colab secret; old Colab secrets named `X-API-Key` and `PATHOLOGY_HUB_API_KEY` were stale and returned 401. In HTTP requests, the header must still be named `X-API-Key`.

## Source-by-source state

### WHO

- User clarified: tag-bearing rows exist in each file under `gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json`.
- Earlier normalized WHO tag artifacts were not confidently located.
- WHO remains upstream/passthrough in current v1.5.8 API; it is not locally vectorized by current project docs.
- Intended curriculum policy: auto-accept WHO→ABPath fuzzy matches at score ≥ 90, audit the mapping, and avoid exposing uncontrolled WHO-local tag hierarchies when a canonical ABPath match exists.

### Textbooks

- Live hybrid FTS+FAISS through `sources=["textbooks"]`.
- Tag repair v2, consolidation v2.1, and governance v10.5 have been performed.
- Current backend-consumed vector docstore path: `gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl`.
- Current backend-consumed manifest path: `gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_manifest.json`.
- Governance removes/hides generated `::Textbooks::`, `Page_`, `Slide_`, file-name tags and uses approved mappings/inheritance instead.
- Page/figure image URLs remain API-exposed where available, but figure junk cleanup remains incomplete.

### PathOut

- PathOut AP-diagnostic v2.3 tag cleanup is live in backend-consumed v1 paths.
- 4,397 local AP-diagnostic vector records.
- PathOut tags are auto-approved as high-quality local curriculum tags unless obvious junk/root problems.
- Do not claim full raw all-site PathOut is fully tagged; the claim is AP-diagnostic vector subset.

### Lectures/videos

- STRICT_CYTO v10.3 reviewed/edited adjudication removed `__UNMAPPED__` from 42,069 routed/vector records.
- v10.5 governance removes lecture artifact tags from returned primary-tag surfaces.
- `video_time_url` may still be null until separate lecture timestamp metadata patch is done.
- Future curriculum hardening should use sequence inheritance for weak lecture/textbook chunks rather than generating new tags.

### Journals

- 103,830 vector records; API-exposed hybrid upstream FTS + FAISS vector.
- No primary-tag registry is claimed.
- Use journals for literature/molecular/biomarker/research context, not curriculum tag coverage unless a journal tagging workstream is added.

## Recommended next step for local Codex

Implement and test a real tag-aware backend layer. The current live API can search evidence and return governed `primary_tag` fields, but no proven live API mode lets the GPT browse `GYN::Ovary` and return all content under that tag.

Codex task:

1. Pull/recover current backend source for `pathology-hub-v04`.
2. Add/load an approved-only SQLite tag index built from governed metadata.
3. Extend `POST /evidence/search` to accept optional tag-aware fields while preserving current behavior.
4. Support `tag_auto`, `tag_exact`, `tag_prefix`, and `tag_browse`.
5. Return `tag_candidates`, `tag_results`, and `tag_facets`.
6. Deploy a new Cloud Run revision and smoke-test with the working key.
7. Only then update GPT Builder schema/instructions.
