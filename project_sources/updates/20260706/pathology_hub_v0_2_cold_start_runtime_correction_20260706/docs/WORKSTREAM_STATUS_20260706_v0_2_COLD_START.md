# Workstream Status — 2026-07-06 — v0_2 Cold-Start Runtime Correction

## Backend API / Cloud Run runtime

Status: **Runtime correction applied and verified.** Production traffic now points
at `pathology-hub-v04-00029-rnt` (100%), which shares an identical container image
digest with the previously-recorded `pathology-hub-v04-00028-guf` and has
`min-instances=1` confirmed actually effective (`MinInstancesProvisioned: True`).
Production code version unchanged: `1.5.10-html-bundle-v0.2-prod`.

Blocked/next: none for this specific issue. A separate, lower-priority, explicitly
monitored-not-fixed observation remains open — see below.

## Evidence RAG (query expansion / root gating / WHO rerank)

Status: **unaffected by this correction.** No application code was changed; the
same v0_2-integrated image that was already benchmarked (996/1008, 12 misses) and
approved for production continues to run, now on a different Cloud Run revision
pointer with a corrected scaling setting.

## Monitored, not yet investigated further: first-live-request WHO warm-up

Status: **observed, documented, explicitly out of scope for this correction.** A
one-time ~27-second delay on the first live `/evidence/search` call touching the
WHO-source code path against a freshly serving instance, with consistently
sub-second repeat calls immediately after. Not a min-instances/cold-container-start
issue (confirmed via logs — no new instance was started during the slow call).

Blocked/next: no action taken or recommended in this package. If this observation
recurs or becomes operationally significant, a future investigation could examine
whether the WHO-upstream client/connection can be pre-warmed at container startup
(this would be an application code change, out of scope for both this correction and
the original v0_2 release).

## Custom GPT frontend

Status: **no action, no change.** This correction is entirely internal to Cloud Run
traffic routing and is invisible to the API contract and to GPT Builder. Still
exactly one Action: `searchEvidence`.

## Release/merge workstream

Status: **unaffected by this correction.** Refer to
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/WORKSTREAM_STATUS_20260705_v0_2.md`
for the current branch/merge state, which this correction does not change.
