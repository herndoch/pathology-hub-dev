# Production Traffic Shift Log — Evidence Search Reliability v0_2 — 2026-07-06

Gradual rollout from the no-traffic candidate (`pathology-hub-v04-00028-guf`) to
100%, per the explicitly approved Phase 9 plan. **No rollback was triggered at any
stage.**

## Stage 0: 0% (candidate deploy, tag-only)

See `docs/PRODUCTION_DEPLOY_LOG_V0_2_20260705.md`. 10/10 smoke tests pass via the
tagged URL before any real traffic was routed to it.

## Stage 1: 10%

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00028-guf=10,pathology-hub-v04-00027-tjm=90 \
  --project=pathology-annotation-project --region=us-central1 --async --quiet
```

Confirmed split: `{'percent': 90, revisionName: '...-00027-tjm'}; {'percent': 10, revisionName: '...-00028-guf'}`.

Verification against the main production URL (load-balanced across both revisions):
5 consecutive `/health` calls -> 5x HTTP 200; 8 consecutive `/evidence/search` (LCIS)
calls -> 8x HTTP 200, `source_status.who: "ok"`, 2 of 8 sampled hit the new revision
(`query_expansion_applied: true`), 0 errors, 0 warnings. **No rollback trigger observed.**

## Stage 2: 50%

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00028-guf=50,pathology-hub-v04-00027-tjm=50 \
  --project=pathology-annotation-project --region=us-central1 --async --quiet
```

Confirmed 50/50 split. 6 consecutive `/health` calls -> 6x HTTP 200, both
`1.5.10-html-bundle` (old) and `1.5.10-html-bundle-v0.2-prod` (new) versions observed,
confirming true load-balanced traffic. 9 `/evidence/search` calls (3 distinct queries x
3 reps, covering who/pathout/textbooks) -> 9x HTTP 200, all `source_status: "ok"`, 0
error flags. **No rollback trigger observed.**

## Stage 3: 100%

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00028-guf=100 \
  --project=pathology-annotation-project --region=us-central1 --async --quiet
```

Confirmed: `{'percent': 100, revisionName: 'pathology-hub-v04-00028-guf', tag: 'v0-2-candidate'}`.

Final validation (`audits/prod_deploy_20260706/final_100pct_smoke/`):
- `/health` -> HTTP 200, `version: 1.5.10-html-bundle-v0.2-prod`, `loaded: true`, all
  4 v0_2 flags `true`.
- 10/10 smoke queries (all sources + figures + HTML bundle) -> HTTP 200, all
  `source_status: "ok"`, LCIS/SSL/CRC/AIS all show `query_expansion_applied: true`
  (v0_2.1 fix confirmed live in production), HTML bundle `html_result` populated.

**No rollback occurred at any stage.** All 3 traffic-shift stages plus the initial
0%-traffic candidate verification passed every health/smoke check cleanly with zero
observed regressions (no non-200s, no `loaded=false`, no `source_status` regression,
no `source_unavailable`, no `/evidence/search` 500s, no figure/HTML bundle
regression).

## Old revision status

`pathology-hub-v04-00027-tjm` (the pre-v0_2 stable revision) still exists, still has
its container image intact, and can be restored to 100% traffic at any time via the
rollback command in `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md` (finalized below
with the actual revision IDs used in this rollout). It was not deleted.
