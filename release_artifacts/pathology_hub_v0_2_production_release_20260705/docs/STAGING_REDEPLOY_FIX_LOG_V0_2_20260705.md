# Staging Redeploy Fix Log — v0_2 Health Responsiveness — 2026-07-05/06

Scope: `pathology-hub-v04-v0-2-staging` only. **Production `pathology-hub-v04` was never
touched during this debugging effort** (confirmed by re-checking `traffic` on the
production service before and after: unchanged, revision `pathology-hub-v04-00027-tjm`,
100%, throughout).

## Cycle 1 (of the 3-cycle budget for this specific issue)

### Diagnosis

1. `gcloud run services describe pathology-hub-v04-v0-2-staging --format=json` -> `Ready=True`,
   only one revision (`00001-s5r`) existed, no crash/failed revision.
2. `gcloud logging read ... freshness=2h` showed a repeating `AUTOSCALING` instance-start
   pattern with `Waiting for application startup` -> `Application startup complete` taking
   consistently ~80-90 seconds per cold instance (heavy `@app.on_event("startup")` corpus
   loading inherited unchanged from verified live production code).
3. No `--min-instances` had been set on the original staging deploy command (defaulted to 0),
   so every idle period causes exactly this ~90s cold-start tax on the next request(s) --
   matching the reported "connects over TLS but does not return promptly" symptom for any
   external prober with a shorter client timeout.
4. A separate finding: an earlier in-session attempt to run
   `gcloud run services update --update-env-vars=EVIDENCE_V0_2_ENABLED=false` (for the
   Phase 6 forced-fallback test) hung locally for ~117 minutes and was manually interrupted.
   Cross-checked against `revisions.list.json`: **no second revision was ever created**,
   proving the hang was a client-side/local CLI polling issue, not a Cloud Run backend
   problem, and confirming `EVIDENCE_V0_2_ENABLED` had remained `true` throughout (never
   actually flipped).

### Fix

```bash
gcloud run services update pathology-hub-v04-v0-2-staging \
  --project=pathology-annotation-project --region=us-central1 \
  --min-instances=1 --async --quiet
```

Used `--async` plus manual bounded polling (`gcloud run services describe ... latestReadyRevisionName`,
10s interval, 150s max) instead of letting the CLI block synchronously, to avoid
repeating the earlier local hang.

**Result:** revision `pathology-hub-v04-v0-2-staging-00002-qtf` became ready in ~80s.
`spec.template.metadata.annotations` confirmed `autoscaling.knative.dev/minScale=1`.

### Verification

- Immediately after rollout, one request still took ~19s (tail end of the deployment's
  instance-replacement cold start — Cloud Run cycles out the rollout instance for a
  steady-state min-instance one shortly after a deploy, which itself needs to cold-start
  once). This is expected and bounded, not an unbounded hang.
- In steady state (no recent deploy), 3 consecutive `/health` calls: `HTTP 200` in
  `0.17s`, `0.16s`, `0.18s`. **Fixed.**

## No application code changes were needed to fix this cycle

The `min-instances=1` change is a pure Cloud Run configuration setting. No files in
`backend/pathology_hub_v04_live_recovered/` were modified as part of this fix (the v0_2
wrapper code was independently confirmed correct throughout — it does not touch corpus
loading at all).

## Forced-fallback test (performed after the health fix, using the same safe async+poll pattern)

1. `--update-env-vars=EVIDENCE_V0_2_ENABLED=false` (async, polled) -> revision `00003-szd` ready.
   Verified `/health` -> `evidence_v0_2_enabled: false`. Verified `/evidence/search` with
   query `"SSL"` on `who` -> `HTTP 200`, `source_status.who: "ok"`, 0 results (baseline
   behavior, matches the original pre-v0_2 miss for a literal "SSL" query), no errors,
   no source made unavailable.
2. `--update-env-vars=EVIDENCE_V0_2_ENABLED=true,EVIDENCE_QUERY_EXPANSION_ENABLED=true,EVIDENCE_ROOT_GATING_ENABLED=true,EVIDENCE_WHO_RERANK_ENABLED=true`
   (async, polled) -> revision `00004-hvf` ready. Verified `/health` -> all 4 flags `true`
   again. Verified `/evidence/search` with query `"LCIS"` on `who` -> `HTTP 200`,
   `query_expansion_applied: true`, 5 results, no warnings.

## Outcome

**Resolved in 1 cycle.** Staging is healthy, fast in steady state, v0_2 confirmed
re-enabled, fallback behavior confirmed correct. Proceeded to Phase 7 (staging benchmark)
after this fix. Current staging revision: `pathology-hub-v04-v0-2-staging-00004-hvf`,
100% traffic, `min-instances=1`, `EVIDENCE_V0_2_ENABLED=true` (and the other 3 flags true).
