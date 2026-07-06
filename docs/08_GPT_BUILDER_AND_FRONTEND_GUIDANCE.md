# GPT Builder and Frontend Guidance — Evidence Search (updated v0_2)

## Current schema

Use `docs/openapi_pathology_hub_unified_searchEvidence_v1_5_10_html_bundle_DRAFT.yaml` or proven v1.5.8 unified schema until v0_2 backend is deployed.

## Action auth

```text
Auth type: API Key
Header name: X-API-Key
Header value: from GCP Secret Manager pathology-hub-api-key (never log or store in artifacts)
```

## Figure retrieval (v0_2 guidance)

- Direct figure URLs usually require **`include_figures=true`** and **`max_figures > 0`**.
- When `include_figures=false`, the API may still return text hits; absence of figures means **figures were not requested**, not that figures are unavailable.
- If the user asks for pictures, figures, images, or photomicrographs, set `include_figures=true` and `max_figures=5` (or up to 10).
- Distinguish in user-facing text: "figures not requested" vs "no figures found for this query."

## Query expansion (backend v0_2)

When deployed with `EVIDENCE_QUERY_EXPANSION_ENABLED=true`, the backend expands governed abbreviations (LCIS, SSL, CRC, CIS, AIS, IPMN, HGSC, etc.) with root/context gating. Clients should still prefer full entity names and organ context when known.

## Behavior until tag-aware API is live

Use staged source-specific searches. Interpret returned governed `primary_tag` as routing/curriculum metadata, not diagnostic proof.

## Safety

- One Action only: `searchEvidence` / `POST /evidence/search`.
- Do not expose API keys in GPT instructions, logs, or saved outputs.
