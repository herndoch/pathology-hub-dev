# Live Version Verification — 2026-07-05

## Claim being verified

Handoff docs assumed live production reports `1.5.10-html-bundle` via `/health`. This session verified that claim directly rather than assuming it.

## Verification

```
$ curl -sS https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/health
{
  "schema_version": "pathology_hub_health.v1.5.10",
  "service": "pathology-hub-v04",
  "version": "1.5.10-html-bundle",
  "loaded": true,
  ...
}
```

HTTP 200. **Confirmed match.** Full redacted response saved at `audits/prod_snapshot_pre_v0_2_20260705/health_response.json` and uploaded to `gs://pathology_hub/06_audits/backend_api/prod_snapshot_pre_v0_2_20260705/health_response.json`.

Cross-checked independently against the recovered source tree (`recovered_backend/v04_10_live_source/app.py`): the terminal version-override block sets `APP_VERSION_V1510 = "1.5.10-html-bundle"` and `base["version"] = APP_VERSION_V1510` in the last-registered `/health` route, and `HTML_BUNDLE_VERSION = "v1.5.10"` matches the health field `html_bundle_version`. Three independent signals (live health call, image digest → Cloud Build source match, and source-code version constant) all agree.

**Conclusion: the assumed live version 1.5.10-html-bundle is CONFIRMED, not assumed.**
