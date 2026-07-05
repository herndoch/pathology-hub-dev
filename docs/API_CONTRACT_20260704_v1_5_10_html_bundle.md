# API Contract — searchEvidence v1.5.10 HTML Bundle

Status: DRAFT until staging smoke tests pass and production promotion is approved.

Endpoint remains:

```text
POST /evidence/search
operationId: searchEvidence
```

No new Action is introduced. Do not create `htmlSearch`, `gallerySearch`, `figureSearch`, or `curriculumSearch`.

## Backward Compatibility

If `render_html` is false or omitted, v1.5.9 behavior is preserved, including curriculum.

Existing sources remain:

```text
who
textbooks
journals
pathout
lectures
videos
curriculum
```

## New Optional Request Fields

```json
{
  "render_html": true,
  "html_profile": "teaching_page",
  "html_title": "Ovarian granulosa cell tumor teaching page",
  "target_figure_count": 10,
  "html_include_toc": true,
  "html_include_source_sections": true
}
```

Field rules:

```text
render_html: boolean, default false
html_profile: teaching_page | gallery | evidence_packet, default teaching_page
html_title: optional string
target_figure_count: integer 1-50, default 10
html_include_toc: boolean, default true
html_include_source_sections: boolean, default true
```

All v1.5.9 fields remain supported:

```text
query
sources
max_results
include_figures
max_figures
compact
excerpt_char_limit
```

## HTML Bundle Behavior

When `render_html=true`, the API:

1. Runs compact internal retrieval using requested sources.
2. Builds a static HTML artifact.
3. Uploads the artifact to:

```text
gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/
```

4. Writes a JSON audit sidecar next to the HTML artifact.
5. Returns a small JSON response with `html_result`.

The API does not return the full HTML body inline and does not return huge figure arrays inline.

## Response Addition

```json
{
  "html_result": {
    "status": "ok",
    "profile": "teaching_page",
    "title": "Ovarian granulosa cell tumor teaching page",
    "html_url": "https://storage.googleapis.com/...",
    "html_gcs_uri": "gs://pathology_hub/...",
    "figure_count": 5,
    "evidence_count": 9,
    "sources_used": ["pathout", "textbooks", "who"],
    "warnings": [],
    "generated_at_utc": "2026-07-04T00:00:00Z",
    "audit_gcs_uri": "gs://pathology_hub/...html.audit.json"
  }
}
```

`status` may be `ok` or `partial`. Gallery requests return `partial` when fewer than `target_figure_count` unique figures are available.

## Safety Rules

- Never invent citations, URLs, image URLs, timestamps, page numbers, or captions.
- Use only returned source links, figure/page URLs, and evidence excerpts.
- Deduplicate figures by URL or caption/source.
- Do not expose rejected, hidden, generated, or forbidden curriculum tags as approved nodes.
- Enforce the curriculum visibility gate when curriculum is requested:

```text
source_status.curriculum == ok
curriculum_status.forbidden_visible_tag_count == 0
```

Forbidden curriculum display patterns:

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

## Health Additions

```text
html_bundle_enabled = true
html_bundle_version = v1.5.10
```
