# GPT Instructions Delta — v0_2 Cold-Start Runtime Correction — 2026-07-06 (no GPT Builder action taken)

This addendum is consistent with, and does not contradict,
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/GPT_INSTRUCTIONS_DELTA_V0_2_20260705.md`
(also mirrored at `docs/GPT_BUILDER_V0_2_INSTRUCTIONS_DELTA_20260705.md`, repo root).

## Headline: no GPT Builder action was taken, and none is required for this correction

This correction was a Cloud Run traffic-routing change between two revisions
sharing an identical container image. It has **zero visibility** to the GPT Action
contract, the request/response schema, or GPT instructions. `searchEvidence`
continues to behave identically from the GPT's perspective before and after this
correction.

## What did NOT change

- Still exactly one Action: `searchEvidence` / `POST /evidence/search`.
- Still the same request/response fields — nothing new for the GPT to send or
  interpret.
- Still the same production code (`1.5.10-html-bundle-v0.2-prod`) — identical image
  digest before and after this correction.

## No new instruction guidance needed

Unlike the original v0_2 release (which introduced the optional
`query_expansion_applied` response field, discussed in the 20260705 package's GPT
instructions delta), this correction introduces **no new response fields and no
behavioral change visible through the API contract.** The one operationally-relevant
effect — production now responding faster and more consistently for most requests,
because `min-instances=1` is finally actually effective — is a pure latency/
reliability improvement, not something requiring any GPT instruction change.

## Mandatory, unchanged guardrails (reaffirmed, not affected by this correction)

Unchanged from the 20260705 package: one Action only; no hallucinated URLs/
timestamps/citations; figures only when requested/relevant; draft/for-review
language for GPT-authored synthesis of evidence content; warnings must be surfaced,
not suppressed.

## Verification performed (this correction)

- Confirmed the traffic-routing change is invisible to the API contract (same
  request/response schema before and after, verified via live health and smoke
  checks against the corrected revision).
- **GPT Builder itself was not opened, edited, or queried at any point during this
  correction.**
