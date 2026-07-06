# Production Deploy Log — Evidence Search Reliability v0_2 — 2026-07-06

**Approval:** Repo owner explicitly approved Phase 8/9 (equivalent to
`APPROVE_PRODUCTION_DEPLOY_EVIDENCE_SEARCH_V0_2`), accepting the 2 documented
non-blocking limitations (BREAST_002/NOS, GU_005) as known/tracked-for-v0_3.
Pre-flight re-verification (`docs/PRODUCTION_PREFLIGHT_REVERIFICATION_20260706.md`)
completed first and passed cleanly (rollback target unchanged, env vars identical to
Phase 0, min-instances confirmed 0/unset).

## Deploy command

```bash
gcloud run deploy pathology-hub-v04 \
  --source=backend/pathology_hub_v04_live_recovered \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --no-traffic \
  --tag=v0-2-candidate \
  --cpu=4 --memory=12Gi \
  --timeout=300 --concurrency=160 --max-instances=10 \
  --env-vars-file=audits/prod_deploy_20260706/prod_env_vars.yaml \
  --set-secrets="PATHOLOGY_HUB_API_KEY=pathology-hub-api-key:latest,OPENAI_API_KEY=OPEN_AI_KEY_01:latest,FIGURE_PROXY_SECRET=pathology-hub-api-key:latest" \
  --async --quiet
```

`--no-traffic --tag=v0-2-candidate`: the new revision receives **zero** production
traffic on deploy and is reachable only via its own tagged URL for isolated
verification, exactly as instructed. `--async` + manual bounded polling used again
(as in Phase 6) to avoid a repeat of the earlier CLI-side hang.

Source: `backend/pathology_hub_v04_live_recovered/` — identical to what was already
validated on staging (byte-identical `app.py`, `evidence_search_reliability_v0_2/`
module, both rule files), differing only in the deploy target (`pathology-hub-v04`
instead of `pathology-hub-v04-v0-2-staging`) and `EVIDENCE_HUB_APP_VERSION_OVERRIDE`
(`1.5.10-html-bundle-v0.2-prod` instead of `...-v0.2-staging`).

## Result

- New revision: **`pathology-hub-v04-00028-guf`**
- Tagged URL: `https://v0-2-candidate---pathology-hub-v04-vorn5q2kga-uc.a.run.app`
- Traffic immediately after deploy: `pathology-hub-v04-00027-tjm` still 100%;
  `pathology-hub-v04-00028-guf` 0% (tag-only), confirmed via
  `gcloud run services describe pathology-hub-v04 --format='value(status.traffic)'`.
- Old stable revision `pathology-hub-v04-00027-tjm` was **not deleted, disabled, or
  otherwise touched** — it continued serving 100% of live traffic throughout this
  deploy step.

## Candidate verification (0% traffic, tagged URL only)

### Health check

```
GET https://v0-2-candidate---.../health -> HTTP 200 in 3.5s
version: 1.5.10-html-bundle-v0.2-prod
schema_version: pathology_hub_health.v1.5.10
loaded: true
evidence_v0_2_enabled: true
evidence_v0_2_module_loaded: true
evidence_v0_2_import_error: null
evidence_query_expansion_enabled: true
evidence_root_gating_enabled: true
evidence_who_rerank_enabled: true
```

(Well within the 120s cold-start tolerance noted in the pre-flight doc; this instance
happened to already be warm from Cloud Run's own readiness checks during the ~100s
polling window while the tag propagated.)

### 10-query smoke suite (same set used on staging)

**10/10 HTTP 200.** Full responses: `audits/prod_deploy_20260706/candidate_smoke/*.json`.

| Test | Result |
|---|---|
| WHO LCIS (expansion) | 200, `query_expansion_applied: true`, 5 results |
| WHO SSL (standalone abbreviation) | 200, `query_expansion_applied: true`, 5 results — v0_2.1 fix confirmed live on production candidate |
| WHO CRC (standalone abbreviation) | 200, `query_expansion_applied: true`, 5 results |
| PathOut AIS (standalone abbreviation) | 200, `query_expansion_applied: true`, 5 results |
| Textbooks (IPMN) | 200, 5 results, hybrid FTS+vector warning present |
| PathOut (melanoma staging) | 200, 5 results |
| Journals (Virchows Archiv) | 200, 0 results for this exact probe (consistent with the same probe's staging result; not a regression -- not part of the scored 1008-row benchmark) |
| Lectures/Videos (thyroid cytology) | 200 |
| Figures (`include_figures=true`) | 200, figures field present and well-formed (0 for this specific melanoma/textbooks probe, matching staging's identical result for the same query) |
| HTML bundle (`render_html=true`) | 200, `html_result` populated |

Behavior is identical to the already-validated staging deployment. No discrepancies.

## Safety confirmation

- GPT Builder was not touched.
- No GCS object was deleted or overwritten (the HTML bundle test wrote one new,
  additive, timestamped object under `gs://pathology_hub/05_html/generated/...`, the
  same expected behavior observed on staging).
- Old stable revision remains fully intact and serving.
