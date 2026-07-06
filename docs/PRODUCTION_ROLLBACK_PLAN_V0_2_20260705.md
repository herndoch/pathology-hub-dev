# Production Rollback Plan — Evidence Search Reliability v0_2 (2026-07-05, finalized 2026-07-06)

**STATUS UPDATE (2026-07-06): Phase 8/9 were explicitly approved and executed.**
Production `pathology-hub-v04` is now at **100% traffic on revision
`pathology-hub-v04-00028-guf`** (the v0_2-integrated revision), deployed and rolled
out per `docs/PRODUCTION_DEPLOY_LOG_V0_2_20260705.md` and
`docs/PRODUCTION_TRAFFIC_SHIFT_LOG_V0_2_20260705.md`. No rollback was needed during
rollout. **The rollback target below is now the PREVIOUS revision** (still intact,
not deleted) in case a rollback is ever needed post-rollout.

The original (pre-rollout) version of this document is preserved below for the
historical record, with the CURRENT exact rollback command called out first.

## CURRENT rollback command (as of 2026-07-06, post-rollout)

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00027-tjm=100 \
  --project=pathology-annotation-project \
  --region=us-central1
```

This restores 100% traffic to `pathology-hub-v04-00027-tjm`, the exact pre-v0_2
revision, which still exists and was not deleted or modified at any point in this
rollout. **A human should re-verify this revision still exists before relying on this
command**, the same way this session re-verified it immediately before Phase 8.

---

## Original plan (2026-07-05, pre-Phase-8) — preserved for the record

## Rollback target (identified in Phase 0, re-verified throughout this session)

| Field | Value |
|---|---|
| Service | `pathology-hub-v04` |
| Region | `us-central1` |
| Project | `pathology-annotation-project` |
| Current (pre-v0_2) revision | `pathology-hub-v04-00027-tjm` |
| Current image | `us-central1-docker.pkg.dev/pathology-annotation-project/pathology-hub/pathology-hub-v04:staging-html-v1-5-10-20260704-r3` |
| Current image digest | `sha256:1d7480629887c8150d40c6de8115c9e48197908759c7fc70ef32e35112a88019` |
| Traffic at time of writing | 100% on `pathology-hub-v04-00027-tjm` (re-verified immediately after Phase 6 staging work; unchanged all session) |

## Exact rollback command

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00027-tjm=100 \
  --project=pathology-annotation-project \
  --region=us-central1
```

This restores 100% traffic to the exact pre-v0_2 revision. Because Cloud Run
revisions are immutable and this revision has not been deleted or modified, this
command is expected to remain valid **as long as no other deploy has happened to
`pathology-hub-v04` between now and the rollback**. **A human must re-verify the
current `latestReadyRevisionName` immediately before Phase 8 to confirm
`pathology-hub-v04-00027-tjm` is still the correct pre-v0_2 rollback target** (see
Go/No-Go doc, confirmation item list).

## Rollback triggers (any one is sufficient)

Per `docs/PRODUCTION_READINESS_MASTER_PLAN_20260705.md` "Rollback criteria" (unchanged,
reaffirmed here):

- Forbidden primary-tag patterns reappear in live searches (v10.5 governance patterns).
- Expected-hit rate on production drops below the v0_1 baseline (979/1008).
- New figure URLs appear when `include_figures=false`.
- `/health` fails or a manifest load error spikes.
- Cross-root wrong-entity retrieval increases (SSL->informatics, CRC->renal, CIS
  cross-organ, etc.).
- Any v0_2-attributable increase in `source_unavailable` responses.

## Rollback procedure (in order)

1. **Fastest mitigation, no deploy required:** if the new production revision has
   `EVIDENCE_V0_2_ENABLED=true` as an env var (per the proposed deploy plan), first try
   `gcloud run services update pathology-hub-v04 --update-env-vars=EVIDENCE_V0_2_ENABLED=false`
   on production. This disables all v0_2 behavior server-side while keeping the new
   revision's other 1.5.10 baseline code running (which is byte-identical to the
   currently-live code otherwise). Verify via `/health` -> `evidence_v0_2_enabled: false`
   and a spot-check `/evidence/search` call.
2. **Full traffic rollback**, if (1) is insufficient or the new revision itself is
   unhealthy: run the exact command above to shift 100% traffic back to
   `pathology-hub-v04-00027-tjm`.
3. **Do not delete** the new v0_2 revision or its image -- leave it in place for
   post-incident analysis; Cloud Run traffic splitting makes this safe (0% traffic,
   revision still exists).
4. **Do not touch GCS.** No embeddings, FAISS indexes, docstores, or raw sources are
   ever modified by a v0_2 rollback -- this is purely an application-layer/traffic
   change. Metadata/manifest rollback, if ever needed for an unrelated reason, uses only
   known backup prefixes (`gs://pathology_hub/99_backups/governance_v10_5/<run_ts>/`,
   `gs://pathology_hub/99_backups/backend_api/`) -- not applicable to a v0_2-only
   incident.
5. **Document the incident** in `06_audits/` with an audit JSON (schema_version,
   trigger observed, rollback command run, timestamp, before/after health checks).

## Estimated rollback time

Traffic-split changes (`update-traffic`) apply in seconds to tens of seconds (no new
container build or cold start required, since the target revision may already have
warm instances or will cold-start in ~90s per this session's own observations --
recommend keeping the old revision's `min-instances` untouched/warm during any Phase 8
canary window specifically so this rollback path stays fast). The env-var-flip option
(1) requires a new revision to be created and will incur the ~90s cold-start window
observed throughout this session before it is the serving revision, unless production
already has `min-instances >= 1` (not verified/changed in this session -- read the
current setting before Phase 8, since if production is currently `min-instances=0`,
option (2) full traffic rollback is faster than option (1) in an active incident).
