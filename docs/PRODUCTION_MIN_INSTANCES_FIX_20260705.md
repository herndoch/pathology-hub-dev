# Production `min-instances` Fix — 2026-07-06

**Scope: scaling-config-only change. No application code deployed, no traffic shift,
no new revision created.** Explicitly approved by the repo owner as a small, scoped
follow-up to Phase 8-10, applying the same fix already proven safe on staging
(`docs/STAGING_REDEPLOY_FIX_LOG_V0_2_20260705.md`).

## Before state

```
$ gcloud run services describe pathology-hub-v04 --format='value(status.traffic)'
{'percent': 100, 'revisionName': 'pathology-hub-v04-00028-guf', 'tag': 'v0-2-candidate', ...}
```

- `autoscaling.knative.dev/minScale`: **not set (effectively 0)**
- `autoscaling.knative.dev/maxScale`: `10`
- `latestReadyRevisionName`: `pathology-hub-v04-00028-guf`
- Image digest: `sha256:05f8a9d17cc19f006efadcd166f0feeb19659b51e3e87302468d86e94b16d62a`
- `/health`: HTTP 200

Full snapshot: `audits/prod_min_instances_fix_20260705/service.before.export.yaml`,
`service.before.describe.json`, `traffic.before.txt`, `health.before.json`.

## Exact command run

```bash
gcloud run services update pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --min-instances=1 \
  --async --quiet
```

`--async` + manual bounded polling used (consistent with every other production write
this session) to avoid CLI-side hangs; polled `latestReadyRevisionName` and
`autoscaling.knative.dev/minScale` every 8s. Confirmed applied on the first poll (~8s).

## After state

- `autoscaling.knative.dev/minScale`: **`1`** (confirmed via `service.after.describe.json`)
- `latestReadyRevisionName`: **`pathology-hub-v04-00028-guf`** — **unchanged**
- Image digest: **unchanged** (byte-for-byte identical to before)
- Traffic: **unchanged** — still `100%` on `pathology-hub-v04-00028-guf`

**No new revision was created by this change.** Cloud Run applied the
`minScale` scaling annotation as an update to the existing serving revision's
configuration without provisioning a new revision object — the `min-instances`
setting is a post-deploy-configurable scaling parameter, distinct from container/image
changes that require a new revision. This was independently verified (not assumed):
image digest, revision name, and traffic split were all diffed programmatically
before vs. after and found identical except for the `minScale` annotation itself.

## Verification after the change

### Health

```
GET https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/health
HTTP 200 in 0.20s
version: 1.5.10-html-bundle-v0.2-prod
loaded: true
evidence_v0_2_enabled: true
evidence_v0_2_module_loaded: true
evidence_query_expansion_enabled: true
evidence_root_gating_enabled: true
evidence_who_rerank_enabled: true
```

Full response: `audits/prod_min_instances_fix_20260705/health.after.json`.

### Smoke test (compact, 2 representative queries)

| Query | Source | HTTP | `source_status` | `query_expansion_applied` |
|---|---|---|---|---|
| LCIS | who | 200 | `ok` | `true` |
| intraductal papillary mucinous neoplasm | textbooks | 200 | `ok` | n/a (already spelled out) |

Full responses: `audits/prod_min_instances_fix_20260705/smoke_who_lcis.json`,
`smoke_textbook_ipmn.json`, `smoke_summary.json`.

## Outcome

**Success, first attempt, no rollback needed.** All 4 v0_2 flags remain `true`, the
serving revision and image are unchanged, traffic remains 100% on
`pathology-hub-v04-00028-guf`, and both health and smoke checks pass cleanly after the
change. Production now has the same `min-instances=1` protection against
scale-to-zero cold starts that was already applied and proven on staging.

## Confirmed untouched

- GPT Builder: not opened or modified.
- GCS indexes/canonical data: no read or write of any kind performed in this task
  beyond the existing `/health` and `/evidence/search` smoke calls (which are the
  same read-only application-level calls used throughout this session).
- Application code: zero changes; `backend/pathology_hub_v04_live_recovered/` is
  unmodified by this task.
- Old rollback-target revision `pathology-hub-v04-00027-tjm`: unaffected, still exists
  at 0% traffic.
