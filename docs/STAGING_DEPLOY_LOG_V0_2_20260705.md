# Staging Deploy Log — v0_2 — 2026-07-05/06

## Target

New Cloud Run service `pathology-hub-v04-v0-2-staging` (never the production
`pathology-hub-v04` service), region `us-central1`, project `pathology-annotation-project`.

## Source

`backend/pathology_hub_v04_live_recovered/` (recovered 1.5.10 baseline + v0_2 wrapper +
`evidence_search_reliability_v0_2/` module + both rule files). Deployed via Cloud Build
(`gcloud run deploy --source`), **no Docker used locally**.

## Exact command (env values are all non-secret GCS/config paths already public in
production's own service description; secrets wired via `--set-secrets`, never printed)

```bash
gcloud run deploy pathology-hub-v04-v0-2-staging \
  --source=backend/pathology_hub_v04_live_recovered \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --allow-unauthenticated \
  --service-account=830130787988-compute@developer.gserviceaccount.com \
  --cpu=4 --memory=12Gi \
  --timeout=300 --concurrency=160 --max-instances=10 \
  --env-vars-file=audits/staging_smoke_20260705/staging_env_vars.yaml \
  --set-secrets="PATHOLOGY_HUB_API_KEY=pathology-hub-api-key:latest,OPENAI_API_KEY=OPEN_AI_KEY_01:latest,FIGURE_PROXY_SECRET=pathology-hub-api-key:latest"
```

`audits/staging_smoke_20260705/staging_env_vars.yaml` contains the 38 plain (non-secret)
production data-plane env vars (GCS index paths, embedding model, pool sizes, promotion
timestamps -- copied verbatim from the Phase 0 production snapshot) plus 7 new v0_2 vars:

```yaml
EVIDENCE_V0_2_ENABLED: "true"
EVIDENCE_QUERY_EXPANSION_ENABLED: "true"
EVIDENCE_ROOT_GATING_ENABLED: "true"
EVIDENCE_WHO_RERANK_ENABLED: "true"
EVIDENCE_V0_2_DEBUG: "false"
EVIDENCE_QUERY_EXPANSION_RULES_PATH: "/app/query_expansion_rules_v0_2_1.json"
EVIDENCE_HUB_APP_VERSION_OVERRIDE: "1.5.10-html-bundle-v0.2-staging"
```

Resource sizing (4 CPU / 12Gi memory / 300s timeout / 160 concurrency / max 10 instances)
matches production exactly, since staging loads the same ~2.8GB of real indexes.
`--min-instances=1` was added in a follow-up update after a health-responsiveness
investigation (see `docs/STAGING_HEALTH_DEBUG_V0_2_20260705.md`).

## Result

```
Service [pathology-hub-v04-v0-2-staging] revision [pathology-hub-v04-v0-2-staging-00001-s5r]
has been deployed and is serving 100 percent of traffic.
Service URL: https://pathology-hub-v04-v0-2-staging-830130787988.us-central1.run.app
```

Full command output: `audits/staging_smoke_20260705/deploy_output.txt`.

## IAM

`--allow-unauthenticated` matches production's own IAM policy (`allUsers` has
`roles/run.invoker` on `pathology-hub-v04`) -- authentication is enforced at the
application layer via the `X-API-Key` header, consistent with the existing
production security model, not via Cloud Run IAM.

## Revision history for this service (through end of Phase 6/health-fix work)

| Revision | Change | Reason |
|---|---|---|
| `00001-s5r` | Initial deploy | v0_2 enabled, no min-instances |
| `00002-qtf` | `--min-instances=1` | Fix scale-from-zero cold-start health responsiveness |
| `00003-szd` | `EVIDENCE_V0_2_ENABLED=false` | Forced-fallback test (Phase 6 requirement) |
| `00004-hvf` | All 4 v0_2 flags restored to `true` | Restore after fallback test |

See `docs/STAGING_REDEPLOY_FIX_LOG_V0_2_20260705.md` for full detail on revisions 2-4.
