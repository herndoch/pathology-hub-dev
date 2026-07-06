# API Contract Addendum — searchEvidence v0_2 — 2026-07-05/06

Addendum to `docs/API_CONTRACT_20260704_v1_5_9_curriculum.md` and
`docs/API_CONTRACT_20260704_v1_5_10_html_bundle.md` (repo root). **The contract those
docs describe is unchanged and still accurate.** This addendum describes only what
v0_2 adds on top.

## Endpoint (unchanged)

```text
POST /evidence/search
operationId: searchEvidence
```

No new Action is introduced. Exactly one Action, confirmed live in production:
`searchEvidence` / `POST /evidence/search`.

## Request fields (unchanged)

All request fields documented in the v1.5.9/v1.5.10 contract docs (`query`,
`sources`, `max_results`, `include_figures`, `max_figures`, `compact`,
`excerpt_char_limit`, `render_html`, `html_profile`, `html_title`,
`target_figure_count`, `html_include_toc`, `html_include_source_sections`) are
**unchanged by v0_2.** No new request field was added. v0_2 operates entirely
server-side on the existing `query` and `sources` values.

## Response fields — new, optional, additive only

| Field | Type | Present when |
|---|---|---|
| `query_expansion_applied` | boolean | Only when governed expansion actually changed the effective query text server-side |
| `warnings` (existing array) | string[] | New entries only appended on internal v0_2 fallback (e.g. `v0_2_who_rerank_failed_baseline_ranking_used: ...`) — never replaces existing baseline warnings |
| `diagnostics.query_expansion_v0_2` | object | Only when `EVIDENCE_V0_2_DEBUG=true` (currently `false` in production) |
| `query_original` / `query_effective` | string | Same debug-only gate as above |

**In the current production configuration, the only externally-visible new field is
`query_expansion_applied` and occasional additional `warnings` entries.**

## Backward compatibility — confirmed, not assumed

The OpenAPI response schema (`docs/openapi_pathology_hub_unified_searchEvidence_v1_5_10_html_bundle_DRAFT.yaml`,
repo root) already declares `SearchEvidenceResponse` with `additionalProperties: true`.
This was checked directly (not assumed) before concluding no schema change is needed:
the new v0_2 fields are additional properties on an already-permissive schema, so they
pass through cleanly to any existing consumer, including the live Custom GPT Action.

**The contract did not break.** Confirmed via:
- Live production smoke tests (10/10) showing identical response shape/behavior to the
  pre-v0_2 baseline for every field already in the contract (`source_status`,
  `figures`, `html_result`, `curriculum_results`, per-source result arrays).
- A forced-fallback test (v0_2 disabled via env flag) on staging, confirming the
  response is byte-for-byte equivalent to pre-v0_2 baseline behavior when v0_2 is off.

## HTML bundle behavior (v1.5.10, unchanged by v0_2)

`render_html`/`html_profile` and the `html_result` response object behave exactly as
documented in `docs/API_CONTRACT_20260704_v1_5_10_html_bundle.md`. Confirmed live in
production: a `render_html=true` smoke test produced a real `html_result.html_url`
pointing at `gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/`.

## Safety rules (unchanged, reaffirmed)

All safety rules in the existing v1.5.10 contract doc (never invent citations/URLs,
deduplicate figures, enforce curriculum visibility gating, forbidden curriculum
display patterns) remain in force and were not touched by v0_2. v0_2 only affects
query expansion and WHO result ordering; it does not touch figure handling,
curriculum gating, or HTML bundle generation logic.

## Health additions (new, this addendum)

```text
evidence_v0_2_enabled: boolean
evidence_v0_2_module_loaded: boolean
evidence_v0_2_import_error: string | null
evidence_query_expansion_enabled: boolean
evidence_root_gating_enabled: boolean
evidence_who_rerank_enabled: boolean
```

Confirmed live in production `/health` as of this release: all 4 boolean flags
`true`, `evidence_v0_2_import_error: null`.
