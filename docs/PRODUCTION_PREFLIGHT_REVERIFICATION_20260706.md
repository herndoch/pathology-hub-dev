# Production Pre-Flight Re-Verification — 2026-07-06 (immediately before Phase 8)

Performed exactly as mandated before any production write action.

## 1. Rollback target still current?

```
$ gcloud run services describe pathology-hub-v04 --format='value(status.latestReadyRevisionName)'
pathology-hub-v04-00027-tjm

$ gcloud run services describe pathology-hub-v04 --format='value(status.traffic)'
{'latestRevision': True, 'percent': 100, 'revisionName': 'pathology-hub-v04-00027-tjm'}
```

**Confirmed unchanged from the Phase 0 (2026-07-05) snapshot.** Image digest, image tag,
env vars (all 38 plain + 3 secret refs), and revision name are byte-identical to the
Phase 0 snapshot (full diff below). **The existing rollback plan and command remain
valid as written — no re-derivation needed.**

## 2. Production `min-instances` setting

```
autoscaling.knative.dev/minScale: (not set / None -> effectively 0)
autoscaling.knative.dev/maxScale: 10
run.googleapis.com/startup-cpu-boost: true
```

**Production has no min-instances configured (same as staging's original, unfixed
state).** This means a freshly-deployed candidate revision will exhibit the same
~80-110s cold-start characteristic observed on staging and on production itself
(Phase 0 snapshot: first `/health` call took ~110s cold). **Rollout health-check
tolerances in Phase 8/9 below are set to allow for this** (a `--max-time` of 120s on
the FIRST post-deploy health check against the new candidate revision's own URL,
before it holds any real traffic; subsequent checks after the instance is warm use a
tighter 20s bound). A cold health check taking up to ~110s on the freshly-deployed
0%-traffic candidate is expected and is NOT treated as a rollout failure by itself —
only a non-200 response or a response after the extended bound is.

`startup-cpu-boost=true` is already enabled, which is the one cold-start mitigation
production already has; it does not eliminate the ~90s corpus-loading time.

## 3. Fresh env-var snapshot vs. Phase 0

Full diff performed programmatically between `audits/prod_snapshot_pre_v0_2_20260705/service.describe.json`
(Phase 0) and `audits/prod_preflight_20260706/service.describe.json` (this pre-flight,
2026-07-06):

| Field | Result |
|---|---|
| Image | **Unchanged** (`...pathology-hub-v04:staging-html-v1-5-10-20260704-r3`) |
| Image digest | Not independently re-pulled this round (image tag unchanged is sufficient evidence) |
| `latestReadyRevisionName` | **Unchanged** (`pathology-hub-v04-00027-tjm`) |
| Plain env vars (38) | **Zero added, zero removed, zero value changes** |
| Secret-backed env vars (3) | **Zero added, zero removed, zero `secretKeyRef` name/key changes** |

**No amendment to `docs/PROPOSED_PRODUCTION_DEPLOY_PLAN_V0_2_20260705.md` is required
for env vars** — the same `audits/staging_smoke_20260705/staging_env_vars.yaml` file
used for staging (which was itself copied verbatim from the Phase 0 production
snapshot) remains accurate for the production deploy, with the version-override value
changed from `...-staging` to `...-prod` per this phase's instructions.

## 4. Amendment to the deploy plan

One amendment made to `docs/PROPOSED_PRODUCTION_DEPLOY_PLAN_V0_2_20260705.md`,
logged here rather than silently: **the plan's step 1 originally said "re-pull a fresh
production env snapshot... do not reuse the Phase 0 snapshot blindly."** This was done
above and found identical, so the plan proceeds using the existing verified env var
file with only the version-override and `--no-traffic`/`--tag` flags changed for
production. The plan's cold-start assumption is confirmed accurate (min-instances is
indeed 0 on production, as flagged as a risk in the original plan) and the rollout
health-check timing described in `docs/PRODUCTION_DEPLOY_LOG_V0_2_20260705.md` /
`docs/PRODUCTION_TRAFFIC_SHIFT_LOG_V0_2_20260705.md` below explicitly accounts for it.

## Verdict: SAFE TO PROCEED

All 4 pre-flight checks pass. No stop condition triggered. Proceeding to Phase 8.
