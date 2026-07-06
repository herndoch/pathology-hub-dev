# Current Master Spine Addendum — Evidence Search Reliability v0_2 Production Release — 2026-07-05/06

Pathology Hub's live Evidence RAG backend (`pathology-hub-v04`) now runs Evidence
Search Reliability v0_2 (governed abbreviation query expansion, anatomic root
gating, and WHO title/subsection reranking) **truly server-side in production**,
not as a client-side simulation as in the prior state described in
`docs/PRODUCTION_READINESS_MASTER_PLAN_20260705.md` (repo root).

## Current live production state

- Service: `pathology-hub-v04`, project `pathology-annotation-project`, region
  `us-central1`.
- **Revision: `pathology-hub-v04-00028-guf`.**
- **Version: `1.5.10-html-bundle-v0.2-prod`.**
- **Traffic: 100%** on this revision.
- **Min-instances: 1** (fixes a scale-to-zero cold-start characteristic of ~90-110s
  that was present on this revision, and on the pre-v0_2 revision, before this fix).
- The current live Action remains `searchEvidence` / `POST /evidence/search` — **one
  Action only**, unchanged, per existing canonical policy.

## Backend source provenance

The backend source now deployed to production
(`backend/pathology_hub_v04_live_recovered/` in the main repo) was **recovered, not
reconstructed**: it was traced from the production Cloud Run image digest to the
exact Cloud Build source tarball that produced it, and independently confirmed to
match the live `/health` version string (`1.5.10-html-bundle`) before v0_2 was added
on top. See `docs/LIVE_BACKEND_RECOVERY_RESULTS_20260705.md` (repo root) for the full
recovery evidence chain.

## Rollback target

`pathology-hub-v04-00027-tjm` — the pre-v0_2 stable revision, still exists, undeleted,
currently at 0% traffic. Exact rollback command:

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --to-revisions=pathology-hub-v04-00027-tjm=100 \
  --project=pathology-annotation-project \
  --region=us-central1
```

## Benchmark state

Live staging benchmark result (same 1008-row query set used for the historical
979/1008 v0_1 baseline): **996/1008 hits (98.81%), 12 misses**. Zero regressions —
every remaining miss is a strict subset of the original 29-miss baseline set. Full
detail in `docs/V0_2_STAGING_BENCHMARK_RESULTS_20260705.md` (repo root).

## Accepted known limitations (explicitly reviewed and approved by Charlie)

- **BREAST_002 / "Invasive ductal carcinoma, NOS"**: an attempted WHO title-boost
  alias fix (mapping "NOS" to WHO 5th-edition "no special type"/"NST" terminology)
  did not resolve this miss — the correct WHO record is apparently not retrieved into
  the candidate pool at all for this exact query, which reranking cannot fix.
  **Accepted as a known limitation; tracked for v0_3 follow-up** (investigate query
  formulation / retrieval pool size, not just reranking).
- **GU_005 / "Nephrogenic adenoma"**: a general WHO title-boost ranking limitation
  (lexically similar but wrong entities outrank the correct one for
  morphology-descriptor-heavy queries). Not attempted this release to avoid
  overfitting a broad ranking heuristic to a single entity. **Accepted as a known
  limitation; tracked for v0_3 follow-up.**

Both were explicitly reviewed and accepted as known/acceptable by Charlie as part of
the Phase 8 production-deploy approval, alongside the 5 other (either intentionally
gated or true-corpus-gap) remaining misses. See
`docs/V0_2_REMAINING_MISS_REGISTER_20260705.md` and
`docs/V0_2_GO_NO_GO_DECISION_20260705.md` (repo root) for full detail.

## GPT Builder / API contract

**Unchanged.** GPT Builder was not opened or modified. The OpenAPI response schema
already declares `additionalProperties: true`, so the new (optional) v0_2 response
fields (`query_expansion_applied`, additional `warnings` entries) pass through
without any schema edit or Action re-import. Exactly one Action remains:
`searchEvidence` / `POST /evidence/search`.

## Branch / merge state

All of this work lives on git branch `production-v0-2-recovery-release-20260705`.
This branch was independently verified merge-ready (8 commits ahead of `master`, zero
divergence since branch creation, all release-package SHA256 checksums verified) but
**has not yet been merged into `master`** — merge is pending Charlie's explicit
approval and manual action. See `docs/MERGE_READINESS_V0_2_20260705.md` (repo root).
