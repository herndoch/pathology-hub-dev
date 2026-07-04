# API Contract — searchEvidence v1.5.9 Curriculum Map FINAL

Status: FINAL for GPT Builder copy/paste after production proof on 2026-07-04.

Production endpoint:

```text
POST https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/evidence/search
operationId: searchEvidence
Auth: X-API-Key
```

## Design Rules

- One Action only: `searchEvidence`.
- No `curriculumSearch` endpoint or Action.
- `query` remains the only required request field.
- v1.5.8 request compatibility is preserved.
- Existing evidence sources remain: `who`, `textbooks`, `journals`, `pathout`, `lectures`, `videos`.
- v1.5.9 adds source: `curriculum`.

## Source Roles

`curriculum` is for navigation: root discovery, node/tag discovery, curriculum map orientation, study structure, and record-count context.

`who`, `textbooks`, `journals`, `pathout`, `lectures`, and `videos` are evidence sources for diagnostic details, definitions, excerpts, links, figures, literature, and teaching content.

Never use curriculum alone as diagnostic evidence.

## Request Schema

```json
{
  "query": "ovary granulosa",
  "sources": ["curriculum"],
  "max_results": 5,
  "include_figures": false,
  "max_figures": 0,
  "compact": true,
  "excerpt_char_limit": 900
}
```

Field rules:

```text
query: required string
sources: optional array; enum who/textbooks/journals/pathout/lectures/videos/curriculum
max_results: optional integer 1-10, default 3
include_figures: optional boolean, default false
max_figures: optional integer 0-10, default 0
compact: optional boolean, default true
excerpt_char_limit: optional integer 200-4000, default 900
```

## Curriculum Response Fields

When `sources` includes `curriculum`, responses may include:

```text
source_status.curriculum
curriculum_status
curriculum_results
warnings
```

Trust curriculum navigation only when:

```text
source_status.curriculum == "ok"
curriculum_status.forbidden_visible_tag_count == 0
```

`curriculum_status` includes:

```text
version = v0.2
build_status = passed_local_visibility_gate
forbidden_visible_tag_count = 0
visible_curriculum_records = 137293
review_queue_count = 4245
rejected_hidden_count = 36284
html_url
gcs_paths_used
```

`curriculum_results[]` are approved visible curriculum nodes only. They may include:

```text
tag
root
status
source_counts
sources
visible_record_count
review_count
example_records
examples
matched_by
score
rank
warning
```

Review queue rows, rejected rows, hidden rows, generated tags, and forbidden-pattern tags are not valid curriculum nodes.

Forbidden patterns:

```text
::Lectures::
::Textbooks::
::Error
Slide_
Page_
Digital_Pathology_Slide
Pathology_Slide
rejected_generated
```

## Recommended GPT Flow

For curriculum/navigation questions:

1. Call `searchEvidence` with `sources:["curriculum"]`.
2. Use returned node/root/tag to refine the user-facing map or to guide evidence calls.
3. If diagnostic details are needed, make a second `searchEvidence` call to evidence sources such as `who`, `textbooks`, `pathout`, `journals`, and `lectures`.

For diagnostic questions:

1. Use evidence sources directly, optionally preceded by curriculum if the scope is ambiguous.
2. Cite or summarize retrieved evidence.
3. Do not cite curriculum nodes as diagnostic proof.

## Production Proof

Production health after deploy reported:

```text
version = 1.5.9-curriculum-map-v02
curriculum_map_enabled = true
curriculum_map_version = v0.2
curriculum_map_build_status = passed_local_visibility_gate
curriculum_map_forbidden_visible_tag_count = 0
curriculum_map_records_visible = 137293
curriculum_map_review_queue_count = 4245
```

Production smoke probes passed for curriculum, who, textbooks, pathout, lectures/videos, and journals.

OpenAPI file for GPT Builder Action schema:

```text
docs/openapi_pathology_hub_unified_searchEvidence_v1_5_9_curriculum_FINAL.yaml
```

GPT instruction file:

```text
docs/GPT_INSTRUCTIONS_PATHOLOGY_HUB_V1_5_9_CURRICULUM_UNDER_8K_FINAL.txt
```
