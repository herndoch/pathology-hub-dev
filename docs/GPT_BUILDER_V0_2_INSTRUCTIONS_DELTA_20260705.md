# GPT Builder Instructions Delta — v0_2 — 2026-07-06 (docs only — GPT Builder not touched)

This document describes what COULD optionally change in the Custom GPT's instructions
to take advantage of v0_2, for human review. **No GPT Builder configuration was
modified by this session** -- this is a proposal document only, per the mission's
explicit out-of-scope rule for GPT Builder mutation.

## What did NOT change (and should not be described differently to the GPT)

- Still exactly one Action: `searchEvidence`.
- Still the same request fields (`query`, `sources`, `max_results`, `include_figures`,
  `max_figures`, `compact`, `render_html`, `html_profile`, etc.) — nothing new to teach
  the GPT to send.
- Still the same core retrieval sources: `who`, `textbooks`, `journals`, `pathout`,
  `lectures`, `videos`, `curriculum`.

## What is now more reliable (optional instruction refinement, not required)

Abbreviation queries (`SSL`, `CRC`, `AIS`, `SCCIS`, `CMF`, `LCIS`, `IPMN`, `DCIS`, etc.)
now benefit from governed server-side expansion with anatomic root gating. This means
the GPT can send these abbreviations directly (as it already does) and now has a
meaningfully higher chance of a hit, without needing any instruction change. **No
instruction change is required for this to work** — it is entirely transparent to the
GPT/user.

## Optional instruction additions (recommended, not required, not executed here)

If the human reviewer wants to make the improvement more explicit to end users, a
narrow, factual instruction addition could be:

> "If the API response includes `query_expansion_applied: true`, you may mention that
> a standard medical synonym or abbreviation expansion was applied to improve
> retrieval, but do not fabricate what the expansion was if it is not shown in the
> response."

This is optional and low-risk since it only references a field that is already present
in the response schema (`additionalProperties: true`).

## Mandatory safety language that must remain in the GPT's instructions (unchanged,
reaffirmed, not newly introduced by v0_2)

The following existing guardrails are **unaffected by v0_2 and must not be weakened**:

1. **Exactly one Action.** The GPT must not be given instructions implying multiple
   search endpoints or operations exist.
2. **No hallucinated URLs, timestamps, or citations.** All `source_url`, `url`,
   `figure_url`, `page_image_url`, and similar fields must come directly from the API
   response — the GPT must never construct or guess a URL, DOI, page number, or
   timestamp that was not returned by `searchEvidence`.
3. **Figures only when explicitly requested/relevant.** The GPT should only include
   image/figure references when `include_figures` was set and the response actually
   contains `figures` or per-result figure URLs — never infer or fabricate figure
   availability.
4. **Draft/for-review language for any generated pathology content.** Any GPT-authored
   synthesis, summary, or gross-template-style text derived from `who_results`,
   `textbook_results`, `journal_results`, or `pathout_results` must be clearly labeled
   as a draft for professional review, not a final diagnosis or authoritative clinical
   statement — consistent with the existing product posture (Evidence RAG is a
   reference/citation tool, not a diagnostic tool).
5. **Warnings must be surfaced, not suppressed.** If the API response includes
   `warnings` (baseline or the new v0_2 fail-open warnings), the GPT should not
   silently discard them if a user's query returned degraded results (e.g. fallback
   to baseline search after a v0_2 internal failure) — at minimum, the underlying
   result should not be presented with unwarranted confidence.

## Verification performed this session

- Confirmed via `docs/OPENAPI_V0_2_ACTION_SCHEMA_DELTA_20260705.md` that the schema
  supports the above without any change.
- Confirmed via live production smoke tests
  (`docs/PRODUCTION_POST_DEPLOY_HEALTHCHECK_V0_2_20260705.md`) that `source_url`,
  `url`, `figure_url`, etc. fields returned by the live API are real, API-sourced
  values (e.g. `https://storage.googleapis.com/pathology-hub-0/WHO/...`,
  `gs://pathology_hub/05_html/generated/...`) — not something a GPT would need to
  invent.
- **GPT Builder itself was not opened, edited, or queried in this session** — this
  document is prepared for a human to review and apply manually if desired.
