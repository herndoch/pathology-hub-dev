# Live State and Proof Summary

Generated: 2026-07-04T18:53:19+00:00

## Live API

```text
Service: pathology-hub-v04
Base URL: https://pathology-hub-v04-vorn5q2kga-uc.a.run.app
Endpoint: POST /evidence/search
Operation ID: searchEvidence
Auth header: X-API-Key
Health: GET /health
```

## API authentication resolution

The Colab secret `X-API-Key` was stale and returned 401. `PATHOLOGY_HUB_API_KEY` was also stale. `HUB_API` matched GCP Secret Manager `pathology-hub-api-key` and returned 200.

Use:

```python
API_KEY = userdata.get("HUB_API")
headers = {"X-API-Key": API_KEY}
```

For GPT Builder, the header name remains `X-API-Key`; paste the working value from `HUB_API`/Secret Manager.

## Final v10.5.2 API proof

```text
Health: 200
Lectures query: 200, forbidden primary_tag count 0
WHO+textbooks+PathOut+journals query: 200, forbidden primary_tag count 0
Textbooks+PathOut query: 200, forbidden primary_tag count 0
GCS proof path: gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json
```

Forbidden patterns checked:

```text
::Lectures::
::Textbooks::
Slide_
Page_
Digital_Pathology_Slide
Pathology_Slide
Benign_Cystic_Neck_Mass_Case_01
::Error
```

The v10.5 notebook-generated output ZIP still contains an earlier proof with 401 results because it read the stale secret. Treat the later v10.5.2 proof as the valid API proof.
