# GPT Builder v0_2 Frontend Test Script — 2026-07-06 (manual, for human execution)

**This is a manual test script for a human to run against the live Custom GPT
Preview. It was NOT executed by this session** (GPT Builder is out of scope for
agent-driven interaction per the mission rules) — it is prepared so a human can
quickly confirm the v0_2-enabled production API behaves correctly from the actual
GPT frontend, complementing this session's direct API-level verification.

## Pre-conditions

- Production `pathology-hub-v04` is now v0_2-enabled at 100% traffic (this session's
  Phase 8/9 work). No GPT Builder change is required for these tests — the existing
  Action configuration already works against the new revision (see
  `docs/OPENAPI_V0_2_ACTION_SCHEMA_DELTA_20260705.md`).

## Test prompts (run each in GPT Preview, record PASS/FAIL)

| ID | Prompt | Expected | What to check |
|---|---|---|---|
| A1 | "Find WHO information on LCIS" | Results about lobular carcinoma in situ | GPT should not need to spell out the full term itself — the abbreviation should already resolve server-side (v0_2 expansion) |
| A2 | "What does SSL mean in GI pathology, and find WHO evidence" | Results about sessile serrated lesion, not SSL/TLS or unrelated content | Confirms root-gated abbreviation expansion firing correctly for a previously-missing case |
| A3 | "Find PathOut evidence on AIS" | Results about cervical adenocarcinoma in situ | Confirms the PathOut-source abbreviation fix |
| B1 | "Search textbooks for intraductal papillary mucinous neoplasm" | Real textbook citations with real source URLs | Confirm no hallucinated citations -- every citation must trace to an actual `source_url`/`url` field |
| C1 | "Show me a figure for melanoma from textbooks" | Either a real figure URL is shown, or the GPT states none was found -- never a fabricated image link | Confirms figure-only-when-requested and no-hallucination guardrails still hold |
| D1 | "Generate a teaching page for ductal carcinoma in situ" | GPT either renders/links the HTML bundle result (`html_result.html_url`) or summarizes evidence, clearly labeled as a study aid / not a final diagnosis | Confirms HTML bundle feature reachable through the GPT and draft-language guardrail holds |
| E1 | "What is bullous pemphigoid, per WHO?" | GPT should report that WHO Classification of Tumours does not contain this (non-tumour) entity, rather than fabricating a WHO citation | This is the one KNOWN documented corpus gap from this release -- the correct behavior is an honest "not found in this WHO corpus" answer, not a hallucinated one |
| E2 | "What is CIS?" (no organ context) | GPT should ask for clarification (bladder? cervix? skin?) rather than guessing, or search broadly across sources without assuming one organ | This is the one KNOWN documented gating limitation (3 plausible roots) -- correct behavior is to not overcommit to a single organ |
| F1 | Any query returning a `warnings` array | GPT should not present results with unwarranted confidence if a warning indicates degraded/fallback behavior | Confirms warning-surfacing guardrail |

## Zero-hallucination spot-check procedure

For any citation/URL the GPT shows in tests B1/D1, a human should independently paste
the URL into a browser (or verify it matches a `source_url`/`url`/`html_url` field in
the raw API JSON, obtainable via `docs/PRODUCTION_POST_DEPLOY_HEALTHCHECK_V0_2_20260705.md`'s
saved smoke responses) to confirm it is real and not invented.

## Pass criteria

All of A1-A3, B1, C1, D1 should return real, API-sourced results with zero
hallucinated URLs/citations. E1/E2 should show the GPT handling the two known
documented limitations honestly rather than confidently inventing an answer. F1
confirms warning-surfacing behavior. Any FAIL should be filed as a GPT
instruction-tuning ticket (not a backend bug, since this session's direct API
verification already confirms the backend itself behaves correctly for the underlying
data).
