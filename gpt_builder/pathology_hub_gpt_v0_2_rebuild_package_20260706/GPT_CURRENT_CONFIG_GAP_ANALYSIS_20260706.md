# GPT Current Config Gap Analysis — v0_2 — 2026-07-06

Compares Charlie's reported current GPT Builder state (given as input — this
session has no GPT Builder access and cannot independently verify any of the
"current state" column) against the recommended v0_2 config in this package.

| Aspect | Current (per Charlie's report) | Recommended (this package) | Gap | Action needed |
|---|---|---|---|---|
| Name | "Pathology Hub GPT — Search Only v1.00" | Same (unchanged) | None | No change required |
| Instructions | Begins "Pathology Hub v1.5.9 instructions" | Begins "Pathology Hub v0_2 instructions", full replacement text in `GPT_INSTRUCTIONS_PATHOLOGY_HUB_V0_2_PASTE_READY.txt` | **Outdated version string and missing v0_2-specific guidance** (staged retrieval direction, short-query preference, `query_expansion_applied` handling, explicit video-timestamp-null handling, workstream-boundary language) | **Replace instructions text** (Step 2 of manual setup) |
| Knowledge panel | "Appears to contain only older GPT builder/API contract files" | 7 curated, current addendum docs (see `GPT_KNOWLEDGE_UPLOAD_MANIFEST_20260706.md`) | **Stale/incomplete** — likely missing all v0_2 and cold-start-correction context; likely still has pre-v0_2 (20260704 or earlier) API contract references that could actively contradict current behavior if the GPT ever reads them | **Remove stale files, upload the 7 recommended files** (Step 3 of manual setup) |
| Action server URL | `pathology-hub-v04-vorn5q2kga-uc.a.run.app` | Same | **None — explicitly verified this URL still correctly resolves to the current production service** (`pathology-hub-v04`, currently serving revision `pathology-hub-v04-00029-rnt`). Cloud Run revision routing is internal and invisible to this URL; no URL change is ever needed purely because the serving revision changed. | No change required |
| Action schema | Presumably the same schema that has worked since v1.5.10 (not independently confirmed) | Same schema, optionally with `query_expansion_applied` explicitly documented | **None functionally** — optional cosmetic-only reimport available, not required | See `GPT_ACTION_SCHEMA_DECISION_20260706.md` — default recommendation is no change |
| Operation count | Presumably 1 (`searchEvidence`) — not independently confirmed, but no evidence of drift | Exactly 1 (`searchEvidence`) | None expected, but **verify during Step 4** of manual setup that only one operation is listed in the Action | Verify (no change expected) |
| "Updates pending" (Charlie's report) | Unspecified pending updates | This entire package IS the resolution for those pending updates | This gap analysis + the rest of this package constitutes the answer to "what updates are pending" | Follow `GPT_BUILDER_MANUAL_SETUP_STEPS_20260706.md` |

## Specific flag: outdated "v1.5.9" version string

If the Instructions field literally still begins with the string "Pathology Hub
v1.5.9 instructions" (matching `docs/GPT_INSTRUCTIONS_PATHOLOGY_HUB_V1_5_9_CURRICULUM_UNDER_8K_FINAL.txt`
in the repo, which is 4253 characters and does not mention v0_2, `query_expansion_applied`,
short-keyword-query preference, staged retrieval, or explicit video-timestamp-null
handling), this is a genuine gap: **the live GPT's instructions are at least two
production releases behind** (missing both the original v1.5.10 HTML-bundle
context, if not already merged in, and all of v0_2). The replacement text in this
package (`GPT_INSTRUCTIONS_PATHOLOGY_HUB_V0_2_PASTE_READY.txt`) is written as a
superset of the v1.5.9 text's good content (curriculum safety gate, forbidden tag
patterns, routing patterns, general answer style) plus the missing v0_2 material —
it is not a from-scratch rewrite, to minimize behavioral drift risk.

## Specific flag: Knowledge panel staleness

Cannot be confirmed independently (no GPT Builder access), but Charlie's own
description ("older GPT builder/API contract files") combined with the confirmed
existence of superseded files in the repo's own history
(`docs/API_CONTRACT_20260704_v1_5_9_curriculum.md`,
`docs/GPT_INSTRUCTIONS_CURRICULUM_MAP_v1_5_9_DRAFT.md`, and any pre-v0_2 OpenAPI
YAML files) makes it likely the Knowledge panel contains at least one of these.
**Recommend Charlie open the panel and remove anything dated 20260704 or earlier**
before uploading the 7 current files.

## Reminder: manual Save/Update action required

**Nothing in GPT Builder takes effect until Charlie clicks the Update/Save button**
after making changes to Instructions, Knowledge, or the Action. This is a manual UI
action that cannot be performed by this session under any circumstance (no GPT
Builder access exists in this environment). This applies separately to each of:
Instructions changes, Knowledge panel changes, and Action schema changes (if the
optional reimport is done) — confirm the Save/Update completes successfully (no
error banner) after each section before moving to the next.

## Overall gap severity assessment

| Gap | Severity | Urgency |
|---|---|---|
| Outdated instructions text | Medium — functional behavior likely still works (v0_2 is transparent server-side), but the GPT is not taking advantage of guidance that would make its behavior more explicit/reliable around query expansion transparency, staged retrieval, and known limitations | Recommended soon, not an emergency |
| Stale Knowledge panel | Low-Medium — depends on whether the GPT actively surfaces Knowledge content to users; if it does, stale API contract details could mislead a user about current capabilities | Recommended alongside the instructions update |
| Action schema | None | No action needed |
| Server URL | None | No action needed |

**No gap found in this analysis rises to the level of "the GPT is currently
answering incorrectly because of a backend problem"** — the backend itself has been
independently verified correct throughout this session's own testing. The gaps here
are entirely about the GPT's own self-description/guidance being behind the current
backend capability, not about broken functionality.
