# Merge Readiness Review — Evidence Search Reliability v0_2 — 2026-07-06

**This is a read-only verification report. No deploy, GCS mutation, GPT Builder
change, merge, or push was performed while producing it.**

## 1. Git status and commit log

```
$ git branch --show-current
production-v0-2-recovery-release-20260705

$ git status
On branch production-v0-2-recovery-release-20260705
nothing to commit, working tree clean
```

**Result: PASS — working tree is clean, no uncommitted changes.**

### Base/default branch identification

```
$ git remote show origin
  HEAD branch: master
```

**The actual default branch is `master`** (not assumed — verified via `git remote show origin`).

### Divergence check

```
$ git rev-parse master
ef8a3d87a536eab975e07cb46a619b2781693ff5
$ git rev-parse origin/master
ef8a3d87a536eab975e07cb46a619b2781693ff5
$ git rev-parse evidence-search-reliability-v0_2-prod
ef8a3d87a536eab975e07cb46a619b2781693ff5
```

`master`, `origin/master`, and `evidence-search-reliability-v0_2-prod` (the branch
this release branch was created from) are **all at the identical commit**
(`ef8a3d8`). `master` has not moved since this release branch was created — there is
**zero divergence**, so this branch is fast-forward-mergeable into `master` with no
merge commit and no conflict risk.

### Commit log (this branch vs. master)

```
$ git log master..production-v0-2-recovery-release-20260705 --oneline
feffd70 Apply staging-proven min-instances=1 fix to production (scaling-config only)
b7d1245 Phase 10: v0_2 production release package
bdd7c1e Phase 9 (frontend): GPT Builder package docs -- no schema/instruction changes needed
0eabd2c Phase 8/9: production deploy and gradual traffic rollout of v0_2 -- 100% complete, no rollback
e20f249 Phase 7: live staging benchmark -- 996/1008 (12 misses, down from 979/1008 baseline); Go/No-Go: GO
5eb1d64 Phase 6: staging deploy + health responsiveness fix + forced-fallback verification
985267b Phase 2-5: canonical recovered backend, server-side v0_2 integration, miss diagnostics, local tests
79bc1e3 Phase 0/1: production snapshot, rollback target, and exact live backend source recovery
```

**8 commits ahead of `master`, 0 commits behind. Result: PASS.**

---

## 2. Release artifact existence and sizes

| Artifact | Path | Size | Status |
|---|---|---|---|
| Handoff doc | `release_artifacts/pathology_hub_v0_2_production_release_20260705/HANDOFF_V0_2_PRODUCTION_RELEASE_20260705.md` | 13,161 bytes | **FOUND** |
| Manifest CSV | `release_artifacts/pathology_hub_v0_2_production_release_20260705/MANIFEST_V0_2_PRODUCTION_RELEASE_20260705.csv` | 4,967 bytes | **FOUND** |
| SHA256SUMS | `release_artifacts/pathology_hub_v0_2_production_release_20260705/SHA256SUMS_V0_2_PRODUCTION_RELEASE_20260705.txt` | 3,910 bytes | **FOUND** |
| Release ZIP | `release_artifacts/pathology_hub_v0_2_production_release_20260705/pathology_hub_v0_2_production_release_20260705.zip` | 79,796 bytes | **FOUND** |
| Release directory | `release_artifacts/pathology_hub_v0_2_production_release_20260705/` | 36 files total (29 in `docs/` subfolder + 7 top-level) | **FOUND** |

**Result: PASS — all 5 required artifacts exist at the expected paths.**

---

## 3. SHA256SUMS verification (recomputed independently, not assumed)

```
$ cd release_artifacts/pathology_hub_v0_2_production_release_20260705
$ sha256sum -c SHA256SUMS_V0_2_PRODUCTION_RELEASE_20260705.txt
./HANDOFF_V0_2_PRODUCTION_RELEASE_20260705.md: OK
./MANIFEST_V0_2_PRODUCTION_RELEASE_20260705.csv: OK
./docs/CURSOR_TRUE_WSL_PREFLIGHT_20260705.md: OK
./docs/GPT_BUILDER_V0_2_FRONTEND_TEST_SCRIPT_20260705.md: OK
[... 30 more files ...]
./docs/WHY_STALE_1_5_7_MUST_NOT_BE_PATCHED_DIRECTLY.md: OK
./miss_diagnostics_20260705.jsonl: OK
./recovered_source_inventory_20260705.txt: OK
./staging_run_cycle_1.json: OK
```

**34/34 files listed in `SHA256SUMS_V0_2_PRODUCTION_RELEASE_20260705.txt` verified
`OK` — zero mismatches, zero missing files. Exit code 0.**

### Informational note (not a failure)

`SHA256SUMS_V0_2_PRODUCTION_RELEASE_20260705.txt` itself and
`pathology_hub_v0_2_production_release_20260705.zip` are **not** among the 34 listed
files (36 total files in the directory − 2 = 34, which matches exactly). This is
expected: the sums file cannot list its own hash, and the ZIP was created after the
sums file was generated (it bundles the already-verified files), so it isn't
independently listed either. Cross-checked separately: the ZIP's SHA256
(`77e1466efc81d68258849efd1f000d1abbf9e8e45f6d2f589b1369a6e411b34b`) matches the value
recorded at creation time in this session's own transcript, confirming it has not
been altered since. **This is noted for completeness, not flagged as a defect.**

---

## 4. Required facts — verified with exact doc + line citations

| # | Fact | Confirmed in | Line(s) |
|---|---|---|---|
| 1 | Revision `pathology-hub-v04-00028-guf` | `docs/PRODUCTION_DEPLOY_LOG_V0_2_20260705.md` | Line 39: `` - New revision: **`pathology-hub-v04-00028-guf`** `` |
| | | `docs/PRODUCTION_TRAFFIC_SHIFT_LOG_V0_2_20260705.md` | Line 49: `` Confirmed: `{'percent': 100, revisionName: 'pathology-hub-v04-00028-guf', tag: 'v0-2-candidate'}`. `` |
| | | `docs/PRODUCTION_POST_DEPLOY_HEALTHCHECK_V0_2_20260705.md` | Line 3: `` **Final production state: 100% traffic on `pathology-hub-v04-00028-guf` `` |
| 2 | Rollback target `pathology-hub-v04-00027-tjm` | `docs/PRODUCTION_ROLLBACK_PLAN_V0_2_20260705.md` | Line 18: `` --to-revisions=pathology-hub-v04-00027-tjm=100 \ `` |
| | | | Line 39: `` \| Current (pre-v0_2) revision \| `pathology-hub-v04-00027-tjm` \| `` |
| 3 | `min-instances=1` | `docs/PRODUCTION_MIN_INSTANCES_FIX_20260705.md` | Line 30: `` --min-instances=1 \ `` |
| | | | Line 40: `` - `autoscaling.knative.dev/minScale`: **`1`** (confirmed via `service.after.describe.json`) `` |
| 4 | Benchmark result 996/1008, 12 misses | `docs/V0_2_STAGING_BENCHMARK_RESULTS_20260705.md` | Line 26: `` \| Hits \| 979/1008 \| 979/1008 \| **996/1008** \| `` (table row; misses = 1008-996 = 12, stated explicitly elsewhere in the same doc, e.g. line 71: `` 29 - 17 = 12. ✓. `` and line 84: `` Because the result (12 misses) already meets the <=14 target ... `` ) |
| 5 | Accepted limitations BREAST_002/NOS and GU_005 | `docs/V0_2_GO_NO_GO_DECISION_20260705.md` | Line 48: `` 2. **Decide on the BREAST_002/NOS miss and the GU_005 ranking limitation**: both are `` |
| | | `release_artifacts/.../HANDOFF_V0_2_PRODUCTION_RELEASE_20260705.md` | Line 204: `` \| BREAST_002 (NOS) \| 2 \| **Attempted fix (WHO title-boost alias), unsuccessful. Accepted as known limitation by repo owner. Tracked as v0_3 follow-up...** \| `` |
| | | | Line 206: `` \| GU_005 (Nephrogenic adenoma) \| 2 \| **General WHO ranking limitation, not attempted this release. Accepted as known limitation by repo owner. Tracked as v0_3 follow-up...** \| `` |

**Result: PASS — all 5 required facts explicitly present with verifiable citations,
not merely asserted.**

---

## 5. Overall verdict

| Check | Result |
|---|---|
| Working tree clean | PASS |
| Base branch correctly identified (`master`, verified not assumed) | PASS |
| Branch fast-forward-able (zero divergence from `master`) | PASS |
| All 5 release artifacts present | PASS |
| SHA256SUMS verification (34/34) | PASS, 0 mismatches |
| ZIP integrity (informational cross-check) | PASS |
| Fact 1 (revision) | PASS |
| Fact 2 (rollback target) | PASS |
| Fact 3 (min-instances=1) | PASS |
| Fact 4 (996/1008, 12 misses) | PASS |
| Fact 5 (accepted limitations) | PASS |

**Overall verdict: CLEAN. No issues or discrepancies found. This branch is ready for
a human to merge, pending their own final review and explicit go-ahead.**

---

## 6. Exact merge command sequence (for Charlie to run himself — NOT executed by this session)

Since `master` has zero divergence from this branch's base, a plain fast-forward
merge is possible and is the cleanest option (no merge commit):

```bash
# 1. Make sure your local master is up to date
git fetch origin
git checkout master
git pull origin master

# 2. Fast-forward merge (will only succeed if master truly hasn't moved --
#    git will refuse and tell you if it can't fast-forward)
git merge --ff-only production-v0-2-recovery-release-20260705

# 3. Push the updated master
git push origin master
```

If you'd prefer an explicit merge commit for audit-trail clarity instead of a silent
fast-forward (reasonable given how much production-affecting work is in this
branch), use this instead of step 2 above:

```bash
git merge --no-ff production-v0-2-recovery-release-20260705 -m "Merge v0_2 production recovery/release branch (Phases 0-10)"
git push origin master
```

**Do not run either sequence without your own explicit review of the branch
contents first.** This session did not execute any of the above commands.
