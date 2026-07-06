# OpenAPI / GPT Action Schema Delta — v0_2 — 2026-07-06

## Headline finding: no OpenAPI schema change is required

The currently-registered GPT Action schema (`docs/openapi_pathology_hub_unified_searchEvidence_v1_5_10_html_bundle_DRAFT.yaml`)
already declares `SearchEvidenceResponse` with `additionalProperties: true`. The v0_2
integration only **adds new, optional response fields** — it does not remove, rename,
or change the type of any existing field, and it does not add any new request field
requirement. Therefore:

- **`SearchEvidenceRequest` is unchanged.** No new required fields; v0_2 operates
  entirely on the existing `query` and `sources` fields server-side.
- **`SearchEvidenceResponse` is unchanged at the schema level** — it already permits
  additional properties, so the new fields below pass through without any schema edit.
- **Exactly one Action remains: `searchEvidence` / `POST /evidence/search`.** No new
  operationId, no new path, no new HTTP method was added anywhere in this release.

## New (optional, additive-only) response fields introduced by v0_2

| Field | Type | When present | Purpose |
|---|---|---|---|
| `query_expansion_applied` | boolean | Only when the governed expansion rules actually changed the effective query text | Lets a caller know abbreviation expansion fired |
| `warnings` (existing array, new entries) | string[] | Only on v0_2 internal failure (fail-open path) | e.g. `v0_2_who_rerank_failed_baseline_ranking_used: ...` — always additive to any existing baseline warnings, never replacing them |
| `diagnostics.query_expansion_v0_2` | object | Only when `EVIDENCE_V0_2_DEBUG=true` (currently `false` in production) | Internal debug info; not exposed in the production configuration deployed in this release |
| `query_original` / `query_effective` | string | Only when `EVIDENCE_V0_2_DEBUG=true` | Same debug-only gate as above |

**In the current production configuration (`EVIDENCE_V0_2_DEBUG=false`), the only
externally-visible new field is `query_expansion_applied` (boolean, optional) and
occasional additional `warnings` array entries on internal fallback.** No GPT Builder
schema update is required to display or use these -- a Custom GPT ignores unknown
optional fields safely per the existing OpenAPI contract's `additionalProperties: true`.

## Recommendation

**No OpenAPI file change, no GPT Builder Action re-import, and no operationId change
are needed for this v0_2 release.** If a future GPT instruction update wants to
explicitly reference `query_expansion_applied` in its reasoning (e.g. "if
query_expansion_applied is true, mention that a synonym was used"), that would be an
instruction-text change only, not a schema change -- see
`docs/GPT_BUILDER_V0_2_INSTRUCTIONS_DELTA_20260705.md`.

## Confirmed: one-Action constraint preserved

Grep of the deployed `backend/pathology_hub_v04_live_recovered/app.py` confirms the
only registered routes are `GET /health` (not a GPT Action, used for infra monitoring
only) and `POST /evidence/search` (operationId `searchEvidence`). No other route was
added by this release.
