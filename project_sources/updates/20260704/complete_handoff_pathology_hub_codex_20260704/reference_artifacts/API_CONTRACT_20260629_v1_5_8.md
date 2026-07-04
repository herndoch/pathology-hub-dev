# API Contract — searchEvidence v1.5.8

## Endpoint

```text
POST https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/evidence/search
```

## Authentication

```text
X-API-Key: <pathology-hub-api-key>
```

## Supported sources

```text
who
textbooks
journals
pathout
lectures
videos
```

## Request

```json
{
  "query": "short keyword-style pathology query",
  "sources": ["textbooks"],
  "max_results": 3,
  "include_figures": false,
  "max_figures": 0,
  "compact": true,
  "excerpt_char_limit": 900
}
```

## Response highlights
Top-level fields may include:

```text
schema_version = evidence_search_response.v1.5.8
source_status
search_mode
who_results
journal_results
pathout_results
textbook_results
lecture_results
video_results
figures
warnings
source_locator_status
page_image_locator_status
```

## Textbook fields
Textbook results may include:

```text
primary_tag
primary_tag_status
primary_tag_basis
page_image_url
page_image_gcs_uri
source_pdf_url
source_page_url
reference_links
candidate_tags
ai_tags
retrieval_mode
vector_score
```

## Journal fields
Journal results may include:

```text
title
journal
source_url / url
doi
excerpt
retrieval_mode
vector_score
```

## PathOut fields
PathOut results may include:

```text
retrieval_mode = pathout_ap_diagnostic_vector for local vector hits
primary_tag
tag_status
vector_score
source_url / url
excerpt
```

## Lecture/video fields
Lecture/video results may include:

```text
primary_tag
tag_status
tagging_scope
vector_score
video_url
video_time_url
start_sec
end_sec
excerpt
```

Known limitation: `video_time_url` often remains null until v04.9 metadata cleanup.
