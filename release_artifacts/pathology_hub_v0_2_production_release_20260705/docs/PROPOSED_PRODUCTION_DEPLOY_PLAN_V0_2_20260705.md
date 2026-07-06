# Proposed Production Deploy Plan — Evidence Search Reliability v0_2 (2026-07-05)

**Status: proposed plan only. NOT executed. Requires explicit human approval
(Phase 8) which this session is not authorized to give or perform.**

## Pre-conditions (must all be true before executing this plan — see Go/No-Go doc)

1. `docs/V0_2_GO_NO_GO_DECISION_20260705.md` recommendation is GO.
2. A human has re-verified `pathology-hub-v04`'s current `latestReadyRevisionName`
   still matches the rollback target recorded in `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md`
   (i.e. no other deploy happened to production between this session and Phase 8).
3. A human has typed the explicit approval phrase referenced in
   `docs/PRODUCTION_READINESS_MASTER_PLAN_20260705.md` (`APPROVE_PRODUCTION_DEPLOY_EVIDENCE_SEARCH_V0_2`)
   or equivalent explicit written approval.

## Proposed steps (for a human/future session to execute — do not run automatically)

### 1. Build and deploy a NEW production revision with v0_2 support code present but DISABLED by default

```bash
gcloud run deploy pathology-hub-v04 \
  --source=backend/pathology_hub_v04_live_recovered \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --no-traffic \
  --tag=v0-2-canary \
  --cpu=4 --memory=12Gi --timeout=300 --concurrency=160 --max-instances=10 \
  --env-vars-file=<production env vars, same 38 as staging, from a FRESH production snapshot -- do not reuse the Phase 0 snapshot blindly, re-pull it> \
  --update-env-vars=EVIDENCE_V0_2_ENABLED=false,EVIDENCE_QUERY_EXPANSION_ENABLED=true,EVIDENCE_ROOT_GATING_ENABLED=true,EVIDENCE_WHO_RERANK_ENABLED=true,EVIDENCE_V0_2_DEBUG=false,EVIDENCE_QUERY_EXPANSION_RULES_PATH=/app/query_expansion_rules_v0_2_1.json \
  --set-secrets="PATHOLOGY_HUB_API_KEY=pathology-hub-api-key:latest,OPENAI_API_KEY=OPEN_AI_KEY_01:latest,FIGURE_PROXY_SECRET=pathology-hub-api-key:latest"
```

Key safety choices:

- `--no-traffic --tag=v0-2-canary`: deploys the new revision receiving **zero**
  production traffic initially, reachable only via its tagged URL
  (`https://v0-2-canary---pathology-hub-v04-<hash>.a.run.app`) for isolated verification.
- `EVIDENCE_V0_2_ENABLED=false` **at first deploy** even though this is the "v0_2
  build" — the master switch stays off until explicitly flipped in step 3, so the
  brand-new production revision is provably byte-identical in behavior to the current
  one before any traffic or flag change.

### 2. Verify the new tagged revision in isolation (zero production traffic impact)

- `curl https://v0-2-canary---.../health` -> confirm `version` and
  `evidence_v0_2_enabled: false`.
- Run the same 10-query smoke set from `docs/STAGING_HEALTH_AND_SMOKE_RESULTS_20260705.md`
  against the tagged URL.
- Confirm `EVIDENCE_V0_2_ENABLED=false` gives byte-identical output to the CURRENT
  production revision for a handful of the same queries (regression proof before any
  flag flip).

### 3. Flip the v0_2 master switch on the (still zero-traffic) canary revision

```bash
gcloud run services update pathology-hub-v04 \
  --project=pathology-annotation-project --region=us-central1 \
  --update-env-vars=EVIDENCE_V0_2_ENABLED=true
```

Re-verify via the tagged URL: `/health` -> `evidence_v0_2_enabled: true`; rerun the
10-query smoke set plus the specific abbreviation queries (SSL/CRC/AIS/SCCIS/CMF/NOS)
that this session's v0_2.1 rules target, confirming `query_expansion_applied: true`
where expected.

### 4. Canary traffic shift (small percentage first)

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=v0-2-canary=5 \
  --project=pathology-annotation-project --region=us-central1
```

Monitor for an operator-defined soak period (recommend >= 1 hour, ideally including
real GPT Action traffic) watching:
- Cloud Run error rate / latency dashboards
- `warnings` fields in logged responses for any `v0_2_*_failed` strings (would indicate
  the fail-open path is triggering more than expected)
- No forbidden-tag or wrong-root complaints

### 5. Progressive traffic increase (only after a clean canary soak)

25% -> 50% -> 100%, with the same monitoring at each step, using
`update-traffic --to-revisions=v0-2-canary=<pct>`.

### 6. Post-deploy verification at 100%

- Re-run the full 1008-query benchmark against production (read-only `/evidence/search`
  calls) to confirm the staging benchmark result holds on production's live index
  state, which may have drifted since the staging benchmark ran.
- Update `docs/LIVE_VERSION_VERIFICATION_20260705.md`-style confirmation for the new
  production version string.

### 7. 24-hour monitoring window

Per the master plan's existing order-of-operations, hold at 100% and monitor for 24h
before considering the v0_2 rollout "complete." Rollback plan
(`docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md`) stays ready throughout.

## What this plan deliberately does NOT do

- Does not touch GPT Builder (separate, out-of-scope workstream).
- Does not add any new OpenAPI operation — the external contract stays exactly
  `searchEvidence` / `POST /evidence/search`.
- Does not delete or overwrite any GCS object.
- Does not skip the canary/soak steps even though staging already validated the code.
