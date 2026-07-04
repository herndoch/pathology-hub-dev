# API Contract — searchEvidence v1.5.9 (curriculum draft)

**Status:** DRAFT — not live until backend deploy + health/API proof.  
**Supersedes (when promoted):** `API_CONTRACT_20260629_v1_5_8.md`  
**Date:** 2026-07-04  
**Workstream:** Custom GPT frontend / API contract (Curriculum Map v0.2)

---

## Design constraints

- **One Action only:** `searchEvidence` → `POST /evidence/search`
- **No separate** `curriculumSearch` Action or endpoint
- **Required request shape unchanged:** `query` remains the only required field
- **Backward compatible:** existing v1.5.8 clients that omit `curriculum` in `sources` behave as today

---

## Endpoint

```text
POST https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/evidence/search
```

*(URL unchanged; curriculum support is an in-place extension of the unified search endpoint.)*

## Authentication

```text
X-API-Key: <pathology-hub-api-key>
```

---

## Supported sources (v1.5.9)

```text
who
textbooks
journals
pathout
lectures
videos
curriculum          ← NEW (draft)
```

### Source roles

| Source | Role |
|--------|------|
| `who`, `textbooks`, `journals`, `pathout`, `lectures`, `videos` | **Evidence** — diagnostic/teaching citations, excerpts, links |
| `curriculum` | **Navigation** — ABPath-governed curriculum nodes, roots, record counts; not final diagnostic proof |

Aliases accepted by backend (unchanged):

- `lecture`, `lectures`, `video`, `videos` → lecture vector search
- `pathology_outlines` → `pathout`

---

## Request

All v1.5.8 fields preserved. Only the `sources` enum grows.

```json
{
  "query": "melanoma invasive overview",
  "sources": ["curriculum"],
  "max_results": 5,
  "include_figures": false,
  "max_figures": 0,
  "compact": true,
  "excerpt_char_limit": 900
}
```

### Field rules (unchanged unless noted)

| Field | Required | Constraints |
|-------|----------|-------------|
| `query` | **yes** | Short keyword-style pathology query |
| `sources` | no | Array; default `["textbooks"]`; each item must be a supported source enum value |
| `max_results` | no | Integer 1–10 (default 3) |
| `include_figures` | no | Boolean (default false) |
| `max_figures` | no | Integer 0–10 (default 0) |
| `compact` | no | Boolean (default true); **supported for curriculum** |
| `excerpt_char_limit` | no | Integer 200–4000 (default 900); ignored for curriculum hits |

### Curriculum-only request example

```json
{
  "query": "GU prostate Gleason",
  "sources": ["curriculum"],
  "max_results": 10,
  "compact": true
}
```

### Two-step navigation + evidence pattern (GPT)

1. **Navigate:** `sources: ["curriculum"]` — find governed nodes/roots/tags  
2. **Detail:** `sources: ["who", "textbooks", "pathout", "journals", "lectures"]` — fetch evidentiary content using refined query/tags from step 1

Both steps use the same `searchEvidence` Action.

---

## Response

`schema_version` (when promoted): `evidence_search_response.v1.5.9`

### Top-level fields (v1.5.8 preserved + draft additions)

```text
schema_version
query
source_status                 ← includes curriculum key when requested
search_mode
who_results
journal_results
pathout_results
textbook_results
lecture_results
video_results
curriculum_status             ← NEW (draft)
curriculum_results            ← NEW (draft)
figures
warnings
source_locator_status
page_image_locator_status
```

Omitted result arrays may be empty or absent when `compact: true` and the source was not requested.

### `source_status` (draft addition)

When `curriculum` is in `sources`:

```json
{
  "curriculum": "ok"
}
```

Allowed values (draft): `ok`, `disabled`, `not_loaded`, `error`, `visibility_gate_failed`

GPT and clients must treat any non-`ok` curriculum status as **not usable for navigation claims**.

### `curriculum_status` (draft)

Structured health/governance summary for the curriculum index backing this response.

```json
{
  "api_exposed": false,
  "index_version": "curriculum_map_v0_2",
  "build_status": "passed_local_visibility_gate",
  "curriculum_node_count": 6105,
  "records_visible_in_curriculum": 137293,
  "forbidden_visible_tag_count": 0,
  "review_queue_count": 4245,
  "records_hidden_rejected": 36284
}
```

**Gate rule:** `forbidden_visible_tag_count` **must be 0** in live health before claiming curriculum is safe to expose. Non-zero → treat curriculum as failed/hidden regardless of HTTP 200.

### `curriculum_results[]` (draft)

Each hit represents a **governed curriculum node**, not a textbook page or lecture chunk.

| Field | Type | Description |
|-------|------|-------------|
| `curriculum_node` | string | Full ABPath-style tag path (e.g. `Skin::Neoplastic::Melanocytic::Malignant::Melanoma_Invasive_Overview_NOS`) |
| `root` | string | Curriculum root (e.g. `Skin`, `GU::Prostate`, `Cyto_GYN`) |
| `record_count` | integer | Visible governed records mapped to this node |
| `status` | string | Governance status (e.g. `approved_abpath`, `mapped_who_abpath`) |
| `match_basis` | string | Optional: `tag_prefix`, `exact_tag`, `fuzzy_who` |
| `score` | number | Optional rank/score when fuzzy matching applies |
| `retrieval_mode` | string | Expected: `curriculum_tag_index` |

`compact: true` may omit null/empty optional fields.

Example:

```json
{
  "schema_version": "evidence_search_response.v1.5.9",
  "query": "melanoma invasive",
  "source_status": {
    "curriculum": "ok"
  },
  "curriculum_status": {
    "api_exposed": true,
    "index_version": "curriculum_map_v0_2",
    "build_status": "passed_local_visibility_gate",
    "curriculum_node_count": 6105,
    "forbidden_visible_tag_count": 0
  },
  "curriculum_results": [
    {
      "curriculum_node": "Skin::Neoplastic::Melanocytic::Malignant::Melanoma_Invasive_Overview_NOS",
      "root": "Skin",
      "record_count": 1400,
      "status": "approved_abpath",
      "retrieval_mode": "curriculum_tag_index"
    }
  ],
  "warnings": []
}
```

---

## Health endpoint expectations (draft)

Before promoting GPT schema or telling users curriculum is live, verify `GET /health` (exact field names subject to backend implementation):

```text
curriculum_api_exposed = true
curriculum_index_version = curriculum_map_v0_2  (or promoted version)
forbidden_visible_tag_count = 0
curriculum_visibility_gate = passed
```

Do **not** rely on local `outputs/curriculum_map_v0_2/acceptance_summary_v0_2.json` alone as proof of API exposure.

---

## Local staging reference (not API proof)

Curriculum Map v0.2 local acceptance (2026-07-04):

| Metric | Value |
|--------|-------|
| `build_status` | `passed_local_visibility_gate` |
| `forbidden_visible_tag_count` | **0** |
| `curriculum_node_count` | 6,105 |
| `records_visible_in_curriculum` | 137,293 |
| `review_queue_count` | 4,245 |
| GCS uploaded/mutated | false |

This validates **local governance only**. It does not prove Cloud Run serves `sources: ["curriculum"]`.

---

## Explicit non-goals (v1.5.9 draft)

- No second GPT Action
- No change to required request fields
- No claim that curriculum nodes replace WHO/textbook/journal/pathout/lecture evidence
- No exposure of review-queue or rejected tags via `curriculum_results`
- No lecture/textbook/slide artifact tags as curriculum nodes (forbidden patterns remain blocked)

---

## Related artifacts

| Artifact | Path |
|----------|------|
| OpenAPI draft | `docs/openapi_pathology_hub_unified_searchEvidence_v1_5_9_curriculum_DRAFT.yaml` |
| GPT instructions draft | `docs/GPT_INSTRUCTIONS_CURRICULUM_MAP_v1_5_9_DRAFT.md` |
| Prior contract | `project_sources/.../API_CONTRACT_20260629_v1_5_8.md` |
| Local acceptance | `outputs/curriculum_map_v0_2/acceptance_summary_v0_2.json` |
| Master spine | `project_sources/.../CURRENT_MASTER_SPINE_20260629_v04_8.md` |
