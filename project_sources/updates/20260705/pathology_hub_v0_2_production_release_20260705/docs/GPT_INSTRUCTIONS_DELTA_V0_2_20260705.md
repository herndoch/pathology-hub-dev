# GPT Instructions Delta — v0_2 — 2026-07-05/06 (docs only — GPT Builder not touched)

This document is a package-local copy/summary, kept **consistent with, and not
contradicting**, the authoritative version at
`docs/GPT_BUILDER_V0_2_INSTRUCTIONS_DELTA_20260705.md` (repo root). Refer to that file
for the full text; this addendum exists so this project-source update package is
self-contained.

## Headline: no GPT Builder action was taken, and none is required for v0_2 to work

`searchEvidence` continues to work exactly as before from the GPT's perspective. The
new v0_2 behavior (governed abbreviation expansion, root gating, WHO rerank) is
entirely server-side and transparent — the GPT does not need any instruction or
schema change to benefit from it.

## What did NOT change

- Still exactly one Action: `searchEvidence` / `POST /evidence/search`.
- Still the same request fields — nothing new for the GPT to send.
- Still the same 7 sources: `who`, `textbooks`, `journals`, `pathout`, `lectures`,
  `videos`, `curriculum`.

## Optional (not required, not executed) instruction refinement

If a human reviewer wants to make the improvement explicit to end users:

> "If the API response includes `query_expansion_applied: true`, you may mention that
> a standard medical synonym or abbreviation expansion was applied to improve
> retrieval, but do not fabricate what the expansion was if it is not shown in the
> response."

This references a field that already exists in the response schema (which permits
additional properties), so it is low-risk, but it is **optional and was not
applied.**

## Mandatory, unchanged guardrails (reaffirmed, not weakened by v0_2)

1. Exactly one Action — no multi-endpoint framing.
2. No hallucinated URLs/timestamps/citations — every link/date must come from the
   actual API response.
3. Figures only when requested/relevant — never inferred or fabricated.
4. Draft/for-review language for any GPT-authored synthesis of evidence content —
   never presented as a final diagnosis.
5. Warnings (baseline or v0_2 fail-open) must be surfaced, not silently discarded.

## Verification performed (this release)

- Confirmed the OpenAPI response schema already permits the new v0_2 fields without
  any change (`SCHEMA_REGISTRY_20260705_v0_2_ADDENDUM.md`, this package; full detail
  in `docs/OPENAPI_V0_2_ACTION_SCHEMA_DELTA_20260705.md`, repo root).
- Confirmed via live production smoke tests that URL/citation fields returned by the
  API are real (e.g. actual `storage.googleapis.com` and `gs://pathology_hub/...`
  paths), not something a GPT would ever need to invent.
- A manual GPT Preview test script is available for a human to run:
  `docs/GPT_BUILDER_V0_2_FRONTEND_TEST_SCRIPT_20260705.md` (repo root). It was not
  executed by any agent session — GPT Builder interaction is out of scope for agent
  work per the canonical rules.

**GPT Builder itself was not opened, edited, or queried at any point during this
release.**
