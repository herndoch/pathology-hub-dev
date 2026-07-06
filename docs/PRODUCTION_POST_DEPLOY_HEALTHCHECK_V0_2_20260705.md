# Production Post-Deploy Health Check — v0_2 — 2026-07-06

**Final production state: 100% traffic on `pathology-hub-v04-00028-guf`
(`1.5.10-html-bundle-v0.2-prod`).**

## Health

```
GET https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/health
HTTP 200
{
  "schema_version": "pathology_hub_health.v1.5.10",
  "version": "1.5.10-html-bundle-v0.2-prod",
  "loaded": true,
  "evidence_v0_2_enabled": true,
  "evidence_v0_2_module_loaded": true,
  "evidence_v0_2_import_error": null,
  "evidence_query_expansion_enabled": true,
  "evidence_root_gating_enabled": true,
  "evidence_who_rerank_enabled": true
}
```

Full response: `audits/prod_deploy_20260706/final_100pct_smoke/health.json`.

## Smoke (10/10 pass)

Full responses: `audits/prod_deploy_20260706/final_100pct_smoke/*.json`,
summary: `audits/prod_deploy_20260706/final_100pct_smoke/summary.json`.

| Query | Source | HTTP | `query_expansion_applied` | `source_status` |
|---|---|---|---|---|
| LCIS | who | 200 | true | ok |
| SSL | who | 200 | true | ok |
| CRC | who | 200 | true | ok |
| AIS | pathout | 200 | true | ok |
| IPMN (spelled out) | textbooks | 200 | n/a | ok |
| melanoma staging | pathout | 200 | n/a | ok |
| Virchows Archiv gastric cancer | journals | 200 | n/a | ok |
| thyroid cytology | lectures/videos | 200 | n/a | ok/ok |
| melanoma (+figures) | textbooks | 200 | n/a | ok |
| ductal carcinoma in situ (+HTML bundle) | who+textbooks | 200 | n/a | ok/ok, `html_result` populated |

## Regression checklist (all explicitly checked, all clean)

- [x] No non-200 responses anywhere in this session's production verification (0%, 10%,
      50%, 100% stages combined: 5 health checks + 8 LCIS + 9 mixed-source + 1 final
      health + 10 final smoke = 33 production HTTP calls, all HTTP 200)
- [x] `loaded: true` confirmed at every health check
- [x] No `source_status` regression (`ok` everywhere requested; `not_requested` for
      sources not in the query, as expected; zero `error`/`upstream_error`/`vector_error`)
- [x] Zero `source_unavailable` occurrences
- [x] Zero `/evidence/search` 500s
- [x] Figure behavior unchanged from staging (figures field present/well-formed when
      requested, 0 leaked when not — same result pattern as the already-validated
      staging deployment for identical probe queries)
- [x] HTML bundle behavior confirmed working (`html_result` with `html_url` populated)
- [x] `query_expansion_applied: true` confirmed for all 4 v0_2.1-targeted standalone
      abbreviations (LCIS, SSL, CRC, AIS) — the exact same live confirmation obtained
      on staging, now reproduced on production

## Old revision status

`pathology-hub-v04-00027-tjm` still exists (undeleted, unmodified), currently at 0%
traffic. Available for immediate rollback per
`docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md`.

## GPT Builder

Not touched at any point in this session. The `searchEvidence` / `POST /evidence/search`
contract is unchanged — same request/response schema, same single Action, no new
operationId.
