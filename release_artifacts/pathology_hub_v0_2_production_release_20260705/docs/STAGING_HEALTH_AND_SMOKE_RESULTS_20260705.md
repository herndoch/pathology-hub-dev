# Staging Health and Smoke Results — v0_2 — 2026-07-05/06

**Service:** `pathology-hub-v04-v0-2-staging`
**Current URL(s):** `https://pathology-hub-v04-v0-2-staging-vorn5q2kga-uc.a.run.app` and
`https://pathology-hub-v04-v0-2-staging-830130787988.us-central1.run.app` (same service)
**Current revision:** `pathology-hub-v04-v0-2-staging-00004-hvf` (100% traffic, `min-instances=1`)

## Deploy

Deployed via `gcloud run deploy --source backend/pathology_hub_v04_live_recovered` (no
Docker; Cloud Build). See `docs/STAGING_DEPLOY_LOG_V0_2_20260705.md` for the exact
command and env vars.

## Health responsiveness incident and fix

Initial deploy (`00001-s5r`) had no `min-instances`, causing ~80-90s cold starts after
idle periods that could appear as a hang to short-timeout probers. Diagnosed and fixed
by setting `min-instances=1` (revision `00002-qtf`). Full diagnosis and fix log:
`docs/STAGING_HEALTH_DEBUG_V0_2_20260705.md` and `docs/STAGING_REDEPLOY_FIX_LOG_V0_2_20260705.md`.
Root cause was infrastructure (scale-to-zero cold start), not an application defect;
zero application code was changed to fix it.

## Health check (steady state, current revision)

```
GET /health -> HTTP 200 in 0.16-0.18s (3 consecutive calls)
version: 1.5.10-html-bundle-v0.2-staging
loaded: true
evidence_v0_2_enabled: true
evidence_v0_2_module_loaded: true
evidence_query_expansion_enabled: true
evidence_root_gating_enabled: true
evidence_who_rerank_enabled: true
```

## 10-query smoke test (all sources + figures + HTML bundle)

Run against revision `00001-s5r` (before the health fix, but functionally identical --
the health fix was infra-only): **10/10 HTTP 200.**

| Test | Source(s) | Result |
|---|---|---|
| WHO abbreviation expansion (LCIS) | who | 200, `query_expansion_applied: true`, 5 results |
| WHO standalone abbreviation (SSL) | who | 200, `query_expansion_applied: true` (v0_2.1 fix confirmed live) |
| WHO standalone abbreviation (CRC) | who | 200, `query_expansion_applied: true` (v0_2.1 fix confirmed live) |
| PathOut standalone abbreviation (AIS) | pathout | 200, `query_expansion_applied: true` (v0_2.1 fix confirmed live) |
| Textbooks (IPMN) | textbooks | 200, 5 results, hybrid FTS+vector warning present |
| PathOut (melanoma staging) | pathout | 200, 5 results |
| Journals (Virchows Archiv gastric cancer) | journals | 200, 5 results |
| Lectures/Videos (thyroid cytology) | lectures | 200, 5 lecture + 5 video results |
| Figures (`include_figures=true`) | textbooks | 200, figures field present and well-formed |
| HTML bundle (`render_html=true`, teaching_page) | who+textbooks | 200, `html_result.html_url` populated, GCS-hosted, `version: 1.5.10-html-bundle-v0.2-staging` |

Full raw responses: `audits/staging_smoke_20260705/*.json`.

## Forced-fallback test (post health-fix, on current revision lineage)

1. `EVIDENCE_V0_2_ENABLED=false` -> revision `00003-szd`: `/health` confirms flag off;
   `/evidence/search` for `"SSL"` on `who` returns `HTTP 200`, `source_status.who: "ok"`,
   0 results (matches pre-v0_2 baseline miss), **no source made unavailable**.
2. Restored `EVIDENCE_V0_2_ENABLED=true` + the other 3 flags -> revision `00004-hvf`:
   `/health` confirms all 4 flags `true` again; `/evidence/search` for `"LCIS"` returns
   `query_expansion_applied: true`, 5 results, no warnings.

## Confirmed: v0_2 is truly server-side enabled

Every check above (`/health` flags, `query_expansion_applied` field, live behavioral
difference between v0_2-enabled and v0_2-disabled revisions for the same "SSL" query)
proves the integration runs inside the deployed Cloud Run service's own request path --
not a client-side replay.

## Production status throughout this entire Phase 6 effort

Re-checked before and after: `pathology-hub-v04` traffic unchanged at
`pathology-hub-v04-00027-tjm` / 100%. **Never touched.**
