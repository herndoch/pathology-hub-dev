# Workstream Status — 2026-07-05/06 — Evidence Search Reliability v0_2 Production Release

## Backend API

Status: **v0_2 server-side integration now LIVE IN PRODUCTION.** Revision
`pathology-hub-v04-00028-guf`, version `1.5.10-html-bundle-v0.2-prod`, 100% traffic,
min-instances=1. Backend source recovered (not reconstructed) and confirmed against
live `/health`. Rollback target `pathology-hub-v04-00027-tjm` preserved, undeleted,
at 0% traffic.

Blocked/next: monitor the standard 24h post-deploy window; consider whether to raise
production `min-instances` further or leave at 1; no other backend-API action
pending.

## Evidence RAG (query expansion / root gating / WHO rerank)

Status: v0_2 rules tuned to v0_2_1 (5 previously-un-expandable standalone
abbreviations fixed via an `allow_standalone` ordering bug fix, plus one WHO
terminology alias attempted). Live staging benchmark: 996/1008 (98.81%), 12 misses,
down from 979/1008 (29 misses), zero regressions.

Blocked/next (v0_3, both explicitly accepted as known/deferred by Charlie):
- BREAST_002/NOS: investigate query-formulation/retrieval-pool-size fix (reranking
  alone did not resolve it).
- GU_005: investigate a more general WHO title-boost weighting change for
  full-title-match vs. token-overlap-match (requires its own full regression pass,
  not a single-entity patch).

## Report-style RAG

Status: unaffected by this release. Out of scope for v0_2 (query
expansion/root-gating/WHO-rerank applies only to the existing `searchEvidence`
sources, which does not include a separate report-style RAG source).

## Gross template generation

Status: unaffected by this release. Out of scope.

## HTML rendering

Status: HTML bundle generation (`render_html`/`html_profile`, introduced in the
recovered 1.5.10 baseline) confirmed preserved and working through the v0_2 wrapper
on both staging and production (verified via live smoke tests producing real
`html_result.html_url` values pointing at
`gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/`).

## Custom GPT frontend

Status: **no GPT Builder action taken.** OpenAPI response schema already permits the
new (optional) v0_2 response fields without any schema change
(`additionalProperties: true`), so no Action re-import is required. Optional,
not-yet-applied instruction refinement suggestions are documented in
`GPT_INSTRUCTIONS_DELTA_V0_2_20260705.md` (this package) /
`docs/GPT_BUILDER_V0_2_INSTRUCTIONS_DELTA_20260705.md` (repo root) for human review.
Still exactly one Action: `searchEvidence`.

## Release/merge workstream

Status: git branch `production-v0-2-recovery-release-20260705` carries all Phase
0-10 work, independently verified merge-ready (clean fast-forward candidate, zero
divergence from `master`, all checksums verified). **Not yet merged** — pending
Charlie's explicit approval and manual `git merge`/`git push`.
