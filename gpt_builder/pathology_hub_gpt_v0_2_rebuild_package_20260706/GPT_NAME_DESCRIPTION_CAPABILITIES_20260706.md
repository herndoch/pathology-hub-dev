# GPT Name / Description / Capabilities — v0_2 — 2026-07-06

## Name

Keep the existing name as reported: **"Pathology Hub GPT — Search Only v1.00"**.

No name change is required by v0_2 (the "Search Only" framing remains accurate —
v0_2 does not add a second capability, only improves the reliability of the
existing one). If Charlie wants to reflect the version bump for internal clarity,
an optional alternative is **"Pathology Hub GPT — Search Only v1.01"**, but this is
purely cosmetic and not required.

## Description (suggested, for the GPT Builder "Description" field)

> Evidence search assistant for pathology reference material (WHO Classification of
> Tumours, textbooks, journals, Pathology Outlines, lectures/videos, and curriculum
> navigation). Retrieves and cites real evidence via a single search Action — does
> not draft final diagnoses or authoritative clinical reports.

This is consistent with the existing "Search Only" framing and does not claim any
capability beyond what `searchEvidence` actually provides.

## Capabilities to enable/disable (GPT Builder settings)

| Capability | Recommendation | Reasoning |
|---|---|---|
| Web Browsing | Leave as currently configured (this session cannot see the current setting) | Not required by v0_2; if currently off, no reason to turn on — Evidence RAG is meant to be corpus-scoped, not open-web |
| Code Interpreter / Data Analysis | Leave as currently configured | Not used by `searchEvidence`; no v0_2 dependency |
| Image generation (DALL-E) | **Recommend OFF if not already** | The product posture (per `docs/GPT_BUILDER_V0_2_INSTRUCTIONS_DELTA_20260705.md` and the existing v1.5.9 instructions) is that figures must only ever be real, API-returned URLs — enabling image generation creates a risk that a user request for "a picture of X" could be answered with a generated (fabricated) image, which directly conflicts with the no-hallucinated-imagery guardrail. If it must stay on for an unrelated reason, the instructions text explicitly forbids using it for pathology figures (see the paste-ready instructions).
| Actions | **`searchEvidence` only** | No change — do not add any other Action |

## Capability boundaries to state explicitly (for the GPT's own self-description
if a user asks "what can you do")

- Can: search WHO/textbooks/journals/PathOut/lectures/videos/curriculum evidence,
  return real citations and figure/page URLs when available, optionally render an
  HTML teaching-page bundle, draft placeholder report language labeled for review.
- Cannot: browse the open web for pathology content, generate synthetic images,
  provide a final sign-out diagnosis, or access any capability outside the single
  `searchEvidence` Action.
- Workstream separation (per canonical project rules): this GPT is the **Custom GPT
  frontend** workstream only. It does not itself perform "report-style RAG," "gross
  template generation," or "HTML rendering" as independent capabilities — those are
  separate backend workstreams that `searchEvidence` may surface results from
  (e.g. `html_result` when `render_html=true`), but the GPT should not claim to
  independently perform them outside of what the Action actually returns.
