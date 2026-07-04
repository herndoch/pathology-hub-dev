# Regression Test Runbook — v1.5.9 Curriculum Map v0.2

Use against staging first. Do not update GPT Builder or production traffic from this runbook.

## Environment

```bash
export BASE_URL="https://STAGING_URL"
export API_KEY="$(gcloud secrets versions access latest --project=pathology-annotation-project --secret=pathology-hub-api-key)"
```

Run:

```bash
python3 scripts/run_curriculum_api_regression_v1_5_9.py
```

## Required Checks

Health must expose:

```text
curriculum_map_enabled = true
curriculum_map_version = v0.2
curriculum_map_build_status = passed_local_visibility_gate
curriculum_map_forbidden_visible_tag_count = 0
curriculum_map_records_visible = 137293
curriculum_map_review_queue_count = 4245
```

Curriculum smoke:

```json
{"query":"GYN::Ovary","sources":["curriculum"],"max_results":5,"compact":true}
```

Curriculum free text:

```json
{"query":"ovary granulosa","sources":["curriculum"],"max_results":5,"compact":true}
```

Forbidden tag regression checks result tags for:

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

Existing source smoke checks:

```text
textbooks
pathout
lectures
who
```

Each should return HTTP 200 with a non-error source status. Result count may vary by query and upstream state, but the endpoint must not reject or remove the existing source.
