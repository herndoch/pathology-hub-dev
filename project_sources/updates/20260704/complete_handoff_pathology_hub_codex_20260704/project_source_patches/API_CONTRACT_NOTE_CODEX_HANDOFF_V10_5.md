# API Contract Note — v10.5 Governed Cleanup

No public Action schema change is proven live from v10.5. Continue using `POST /evidence/search` with header `X-API-Key`.

The working API key value in Colab was stored under `HUB_API`; old values under `X-API-Key` and `PATHOLOGY_HUB_API_KEY` were stale.

Future tag-aware work should preserve the existing endpoint and add optional request fields only after backend support is deployed.
