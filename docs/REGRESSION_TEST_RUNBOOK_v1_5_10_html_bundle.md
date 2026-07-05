# Regression Test Runbook — v1.5.10 HTML Bundle

Run against staging first:

```text
https://pathology-hub-v04-html-staging-830130787988.us-central1.run.app
```

Set:

```bash
BASE_URL="https://pathology-hub-v04-html-staging-830130787988.us-central1.run.app"
API_KEY="$(gcloud secrets versions access latest --secret=pathology-hub-api-key --project=pathology-annotation-project)"
```

## Smoke Tests

Normal curriculum:

```json
{"query":"ovary granulosa","sources":["curriculum"],"max_results":5,"compact":true}
```

Normal textbook:

```json
{"query":"prostate adenocarcinoma cribriform pattern","sources":["textbooks"],"max_results":1,"compact":true}
```

HTML teaching page:

```json
{"query":"ovarian granulosa cell tumor","sources":["who","textbooks","pathout"],"max_results":3,"compact":true,"include_figures":true,"max_figures":5,"render_html":true,"html_profile":"teaching_page","html_title":"Ovarian granulosa cell tumor teaching page"}
```

Expected: `html_result.status == "ok"`, `html_url` present, `audit_gcs_uri` present, response is small.

HTML gallery:

```json
{"query":"tubular adenoma","sources":["textbooks"],"max_results":5,"compact":true,"include_figures":true,"max_figures":10,"render_html":true,"html_profile":"gallery","html_title":"Tubular adenoma gallery","target_figure_count":50}
```

Expected: `html_result.status` is `ok` or `partial`, `html_url` present, `audit_gcs_uri` present, `figure_count` reported, warning if fewer than 50 figures are available.

## Response Size Regression

Confirm the JSON response:

- does not include full HTML body
- does not include giant figure arrays
- includes `html_result.html_url`
- includes `html_result.audit_gcs_uri`

## Forbidden Pattern Scan

Scan returned JSON and downloaded/generated HTML for:

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

The scan should return no curriculum node display hits.
