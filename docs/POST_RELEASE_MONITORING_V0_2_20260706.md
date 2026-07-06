# Post-Release Monitoring — Evidence Search Reliability v0_2 — 2026-07-06

**This is a read-only verification report. No Cloud Run config, GCS object, or GPT
Builder configuration was changed while producing it.**

## 1. Local git state (verified, not assumed)

```
$ git branch --show-current
master

$ git status --short
?? project_sources_upload_20260705_v0_2/

$ git log --oneline --decorate -5
14a687b (HEAD -> master, origin/master, origin/HEAD) Merge v0_2 production recovery release without generated audit artifacts
ef8a3d8 (evidence-search-reliability-v0_2-prod) Add HTML bundle staging implementation v1.5.10
45661e5 Finalize GPT Builder curriculum v1.5.9 package
207bdb3 Add Curriculum Map v1.5.9 API implementation
6c4012e Add Curriculum Map v0.2 staging manifest
```

**The user's stated context ("master has been updated") is confirmed true, but with
an important technical nuance that must be reported precisely rather than papered
over:**

- `master` now includes a commit (`14a687b`, authored by Charlie directly, already
  pushed to `origin/master`) titled "Merge v0_2 production recovery release without
  generated audit artifacts."
- **This is NOT a standard two-parent git merge commit.** `git log -1 --format='%P'
  14a687b` shows exactly **one parent** (`ef8a3d8`), meaning it is a squash-style
  commit (all changes applied and committed as a single new commit on top of
  `master`'s prior tip), not a merge that preserves `production-v0-2-recovery-release-20260705`'s
  12 individual commits as ancestors.
- **Explicit check performed:** `git merge-base --is-ancestor
  production-v0-2-recovery-release-20260705 master` returns **false**. The original
  feature branch's tip commit is **NOT reachable from `master`** in the strict git
  ancestry sense, even though its *content* has been incorporated.
- **Content verification:** diffed `master` against the common base (`ef8a3d8`) and
  against `production-v0-2-recovery-release-20260705` against the same base.
  `master`'s squash commit changes **309 files** (65,383 insertions) vs. the original
  branch's **550 files** (3,575,790 insertions). The **241-file difference is
  entirely accounted for by files under `06_audits/`** (bulky, generated audit
  artifacts from an unrelated prior-session curriculum/enrichment workstream — matches
  the commit message "without generated audit artifacts"). **Zero files in `master`
  are missing from the original branch, and zero critical `backend/` or `tests/`
  source files were excluded.** Confirmed present in `master`:
  `backend/pathology_hub_v04_live_recovered/app.py`,
  `docs/V0_2_GO_NO_GO_DECISION_20260705.md`, `docs/MERGE_READINESS_V0_2_20260705.md`,
  and the `project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/`
  package.
- **Conclusion: `master` substantively and completely contains all load-bearing
  v0_2 release work.** The only technical caveat is that this was done via a
  squash-style commit rather than a real `git merge`, so branch ancestry tools will
  report "not merged" even though the content is present. `production-v0-2-recovery-release-20260705`
  still exists as a local branch and was not deleted.
- **One untracked local artifact was observed and not committed by this task:**
  `project_sources_upload_20260705_v0_2/` — a flat directory containing copies of the
  8 addendum docs from `project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/`
  plus a `SHA256SUMS_PROJECT_SOURCE_UPLOAD_20260705_v0_2.txt`. This appears to be a
  manually-prepared flat export for the user's stated "uploaded to ChatGPT Project
  Sources" action. **This session cannot verify the actual ChatGPT upload claim**
  (no access to ChatGPT/Project Sources) — only that a local staging folder consistent
  with that claim exists on disk, untracked by git.

## 2. Production health check (read-only)

```
GET https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/health
```

**Result: intermittently slow, but ultimately healthy and correct — reported
honestly, not glossed over.**

| Attempt | Client timeout | Result |
|---|---|---|
| 1 | 30s | **Timed out, no response** (curl exit 28) |
| 2 | 60s | **Timed out, no response** (curl exit 28) |
| 3 | 150s | HTTP 200 in **10.5s** |

Cross-checked against Cloud Run logs for the same window (read-only `gcloud logging
read`, no config change): two new container instances were started via
`AUTOSCALING` (`"Instance started due to configured scaling factors... or no
existing capacity for current traffic"`) at approximately the same times as attempts
1 and 2, each taking **~90-100 seconds** to reach `Application startup complete`
before serving any request. This is consistent with attempts 1 and 2 having been
in-flight against a cold-starting instance when the client gave up, rather than a
server-side error (no 5xx observed; the eventual successful attempt returned fully
correct content).

**Concerning finding, reported plainly:** production has `min-instances=1`
configured (re-verified read-only: `autoscaling.knative.dev/minScale: 1`), which is
intended to keep at least one instance always warm. The fact that **two
`AUTOSCALING`-triggered cold starts still occurred** during this check suggests
min-instances=1 alone did not fully prevent a cold-start-class delay at this moment
-- possibly because the guaranteed warm instance was busy/unavailable when these
specific requests arrived, or because of a Cloud Run instance-cycling event unrelated
to this session. **This session did not investigate further or change any
configuration** (explicitly out of scope for this read-only task) but flags it as a
genuine, unresolved, worth-following-up production observation -- see the
recommended next steps in `docs/NEXT_SAFE_WORK_ORDER_AFTER_V0_2_20260706.md`.

### Health content (from the successful attempt 3)

```json
{
  "version": "1.5.10-html-bundle-v0.2-prod",
  "schema_version": "pathology_hub_health.v1.5.10",
  "loaded": true,
  "evidence_v0_2_enabled": true,
  "evidence_v0_2_module_loaded": true,
  "evidence_v0_2_import_error": null,
  "evidence_query_expansion_enabled": true,
  "evidence_root_gating_enabled": true,
  "evidence_who_rerank_enabled": true,
  "evidence_v0_2_debug": false
}
```

Revision (`pathology-hub-v04-00028-guf`) and traffic (100%) reconfirmed via
`gcloud run services describe` (read-only): unchanged from the end of the prior
release session.

## 3. Production smoke tests (read-only `POST /evidence/search`)

### Test 1: LCIS breast, `sources: ["who", "textbooks"]`

| Field | Result |
|---|---|
| HTTP status | 200 |
| Elapsed | 34.5s (slower than the sub-1s warm baseline seen previously in this release; likely related to the same intermittent cold-path behavior noted above -- reported honestly, not assumed benign) |
| `source_status` | `{"who": "ok", "textbooks": "ok", ...}` |
| `who_results` | 5 |
| `textbook_results` | 5 |
| `query_expansion_applied` | `true` |
| `warnings` | Only the standard textbook hybrid-retrieval advisory warnings (no error/fallback warnings) |

**PASS**, with a responsiveness caveat noted above.

### Test 2: IPMN pancreas, `include_figures: true`, `sources: ["textbooks"]`

| Field | Result |
|---|---|
| HTTP status | 200 |
| Elapsed | 0.77s |
| `source_status` | `{"textbooks": "ok", ...}` |
| `textbook_results` | 5 |
| `figures` | 5 (correctly populated since `include_figures=true`) |
| `query_expansion_applied` | `true` |
| `warnings` | Only the standard textbook hybrid-retrieval advisory warnings |

**PASS**, fully responsive.

## 4. Overall assessment

- **Functional correctness: PASS.** Both smoke queries returned correct, complete
  results with v0_2 query expansion confirmed active server-side, exactly as
  expected from the prior release verification.
- **Responsiveness: MIXED.** Two of three initial `/health` probes and one of two
  `/evidence/search` smoke tests experienced longer-than-expected latency
  consistent with cold-start behavior, despite `min-instances=1` being correctly
  configured. This is reported as a genuine open observation, not resolved in this
  task (no Cloud Run config changes were made or are authorized here).
- **No external state was changed** by this monitoring task. All actions were
  read-only `GET`/`POST` calls to the existing production API and read-only
  `gcloud run services describe` / `gcloud logging read` calls.
