# GPT Action Schema Decision — v0_2 — 2026-07-06

## Plain statement of the decision

**The existing Action definition can remain untouched. A reimport is NOT required
for v0_2 to function correctly.** This is a low-risk, low-effort situation: no
schema edit, no server URL change, no operationId change.

**However, a low-risk reimport is optionally recommended** for two narrow, cosmetic
reasons only (detailed below) — not because anything is broken.

## Why no new endpoint/Action is needed for v0_2

1. **The request schema is unchanged.** v0_2 operates entirely server-side on the
   existing `query` and `sources` fields already defined in the Action's
   `SearchEvidenceRequest` schema. No new request field is required to trigger v0_2
   behavior (query expansion, root gating, WHO rerank all happen automatically
   inside the backend for every request).
2. **The response schema is additive-only, and already permits this.** The
   currently-registered schema
   (`docs/openapi_pathology_hub_unified_searchEvidence_v1_5_10_html_bundle_DRAFT.yaml`,
   repo root, and the recommended current copy in this package,
   `GPT_ACTION_OPENAPI_CURRENT_RECOMMENDED.yaml`) declares:
   ```yaml
   SearchEvidenceResponse:
     type: object
     additionalProperties: true
   ```
   **`additionalProperties: true` is the key fact.** This tells the Action's response
   parser (and the GPT's own interpretation of the JSON) that unlisted fields are
   valid and should not cause a parse error or be silently dropped as
   schema-violating. v0_2's one new externally-visible field in the current
   production configuration, `query_expansion_applied` (boolean), passes through
   exactly like this. Confirmed live: `docs/OPENAPI_V0_2_ACTION_SCHEMA_DELTA_20260705.md`
   (repo root).
3. **Exactly one Action remains: `searchEvidence` / `POST /evidence/search`.** No new
   path, no new HTTP method, no new operationId. Verified directly against the
   deployed backend source (`backend/pathology_hub_v04_live_recovered/app.py`,
   repo root) — only `GET /health` (not a GPT Action) and `POST /evidence/search`
   (operationId `searchEvidence`) are registered.

## If a reimport IS done anyway (optional, cosmetic only)

If Charlie chooses to reimport the schema anyway (e.g. to explicitly document the
`query_expansion_applied` field in the schema for clarity, rather than relying
purely on `additionalProperties: true`):

- **The same server URL must be preserved:**
  `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app`
- **The same operationId must be preserved:** `searchEvidence`
- **The same single path must be preserved:** `POST /evidence/search`
- Use `GPT_ACTION_OPENAPI_CURRENT_RECOMMENDED.yaml` (this package) as the exact
  schema to paste/import — it is the existing repo schema
  (`docs/openapi_pathology_hub_unified_searchEvidence_v1_5_10_html_bundle_DRAFT.yaml`)
  with `query_expansion_applied` explicitly documented as an optional response
  property (purely for clarity/self-documentation — `additionalProperties: true`
  already made this safe without the explicit property).
- After reimport, GPT Builder will re-validate the schema; confirm no validation
  errors appear, then click Update/Save (manual UI action Charlie must perform).

## Recommendation

**Do not reimport unless Charlie specifically wants the `query_expansion_applied`
field self-documented in the schema for clarity.** The functional behavior is
identical either way — reimporting is purely optional polish, not a requirement,
and every hour of engineering time is better spent on the Preview QA testing in
`GPT_PREVIEW_QA_PROMPTS_V0_2_20260706.md` than on a schema change that changes
nothing observable.
