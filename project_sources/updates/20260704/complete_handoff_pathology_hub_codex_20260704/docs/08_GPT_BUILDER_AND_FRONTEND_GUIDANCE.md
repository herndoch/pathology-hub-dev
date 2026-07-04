# GPT Builder and Frontend Guidance

## Current schema

Use current proven `openapi_pathology_hub_unified_searchEvidence_v1_5_8.yaml` until tag-aware backend is deployed.

## Action auth

```text
Auth type: API Key
Header name: X-API-Key
Header value: working HUB_API / GCP Secret Manager pathology-hub-api-key value
```

## Behavior until tag-aware API is live

Use staged source-specific searches. Interpret returned governed `primary_tag` as routing/curriculum metadata, not diagnostic proof. Do not expose generated lecture/textbook artifact tags as curriculum concepts.

## After tag-aware backend is live

Install tag-aware OpenAPI only after health/regression tests prove tag modes are live.
