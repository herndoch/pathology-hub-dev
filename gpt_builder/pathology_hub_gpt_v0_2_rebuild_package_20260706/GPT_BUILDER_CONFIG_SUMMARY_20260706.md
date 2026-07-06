# GPT Builder Config Summary — Pathology Hub GPT v0_2 Update — 2026-07-06

**This entire package is documentation/prep material only. It was NOT applied to
GPT Builder by this session — GPT Builder is out of agent reach entirely. Every step
below requires Charlie to perform manually in the GPT Builder UI.**

## What backend state this package reflects (verified, not fabricated)

| Field | Value |
|---|---|
| Service | `pathology-hub-v04` |
| Live revision | `pathology-hub-v04-00029-rnt` |
| Version | `1.5.10-html-bundle-v0.2-prod` |
| Traffic | 100% |
| Min-instances | 1, confirmed effective (`MinInstancesProvisioned: True`) |
| Action | exactly one: `searchEvidence` / `POST /evidence/search` |
| Schema change needed for v0_2? | **No** — response schema already permits additional properties |
| New optional response field | `query_expansion_applied` (boolean) |
| Known accepted limitations (v0_3-tracked) | `BREAST_002`/NOS, `GU_005` |

Sources: `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`,
`docs/OPENAPI_V0_2_ACTION_SCHEMA_DELTA_20260705.md`,
`docs/V0_3_BACKLOG_FROM_V0_2_LIMITATIONS_20260706.md` (all repo root), and the
`project_sources/updates/20260705/` and `project_sources/updates/20260706/`
packages.

## What Charlie reported about the CURRENT live GPT (given as input, not
independently verifiable by this session)

- Name: "Pathology Hub GPT — Search Only v1.00"
- Instructions text begins "Pathology Hub v1.5.9 instructions" (this matches a real
  file already in the repo: `docs/GPT_INSTRUCTIONS_PATHOLOGY_HUB_V1_5_9_CURRICULUM_UNDER_8K_FINAL.txt`
  — so this report is internally consistent with known repo history)
- Knowledge panel appears to contain only older files
- Action server URL: `pathology-hub-v04-vorn5q2kga-uc.a.run.app`
- Updates pending

## Server URL check (explicitly verified, not assumed)

The Action's configured server URL, `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app`,
**is the correct, currently-live URL for the same Cloud Run service** —
`pathology-hub-v04`'s "friendly" (hash-based) URL form. This URL was used
throughout this session's own production verification (see
`docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`) and resolved correctly to the
current serving revision (`pathology-hub-v04-00029-rnt`) at the time of this
writing. **No Action server URL change is needed** — the same service continues to
serve this URL regardless of which revision is receiving traffic underneath it,
since revision routing is internal to Cloud Run and invisible to callers.

## Recommendation: update the existing GPT directly, OR clone-test-first?

**Recommendation: clone-test-first, then promote.** Reasoning:

1. **This is described as a live, presumably-in-use GPT** ("Pathology Hub GPT —
   Search Only v1.00"). Directly editing a production-facing GPT's instructions and
   Knowledge risks a visible regression for any current user mid-session if the new
   instructions text has an unnoticed issue (e.g. a routing mistake, a guardrail
   accidentally weakened, or a Knowledge file conflict).
2. **The Action itself does not need to change** (same URL, same schema, same one
   Action) — so the risk is entirely in the instructions-text and Knowledge-panel
   changes, which are exactly the parts a clone-and-Preview-test workflow protects
   against.
3. GPT Builder natively supports duplicating a GPT ("Duplicate" from the GPT's
   context menu / editor), which creates a private copy with its own Preview pane,
   fully isolated from the live GPT's current users, at zero cost/risk.
4. Once the QA prompts in `GPT_PREVIEW_QA_PROMPTS_V0_2_20260706.md` all pass against
   the CLONE (scored per `GPT_PREVIEW_SCORING_RUBRIC_V0_2_20260706.md`), Charlie can
   either (a) copy the validated instructions/Knowledge from the clone into the
   original live GPT, or (b) promote the clone itself if GPT Builder's sharing/link
   configuration allows a clean swap — whichever is operationally simpler for
   Charlie's actual GPT Store/sharing setup (this session cannot see that
   configuration, so both options are noted).
5. **Do NOT delete or unpublish the original GPT during this process** — the clone
   workflow is additive/parallel, not a replace-in-place.

**Only if** Charlie judges the current GPT has effectively no active users right now
(e.g. it's a personal/internal tool, not yet shared broadly) would a direct in-place
update be reasonable to skip the clone step — that judgment call belongs to Charlie,
not this session, since usage/audience is not something this session can verify.

## What this package does NOT do

- Does not touch GPT Builder itself (no API/browser access to GPT Builder exists in
  this environment).
- Does not change the Action's OpenAPI schema in a way that requires a reimport
  (see `GPT_ACTION_SCHEMA_DECISION_20260706.md` for the precise reimport
  recommendation).
- Does not implement any v0_3 backend change.
- Does not modify GCS or Cloud Run.

## Files in this package

| File | Purpose |
|---|---|
| `GPT_BUILDER_CONFIG_SUMMARY_20260706.md` | This file |
| `GPT_NAME_DESCRIPTION_CAPABILITIES_20260706.md` | Suggested name/description/capabilities text |
| `GPT_INSTRUCTIONS_PATHOLOGY_HUB_V0_2_PASTE_READY.txt` | Paste-ready instructions text |
| `GPT_KNOWLEDGE_UPLOAD_MANIFEST_20260706.md` | Which files to upload/remove from the Knowledge panel |
| `GPT_ACTION_SCHEMA_DECISION_20260706.md` | Whether/why the Action needs reimport |
| `GPT_ACTION_OPENAPI_CURRENT_RECOMMENDED.yaml` | The recommended current OpenAPI schema |
| `GPT_BUILDER_MANUAL_SETUP_STEPS_20260706.md` | Step-by-step manual instructions for Charlie |
| `GPT_PREVIEW_QA_PROMPTS_V0_2_20260706.md` | Test prompts for the Preview pane |
| `GPT_PREVIEW_SCORING_RUBRIC_V0_2_20260706.md` | How to score each QA prompt |
| `GPT_CURRENT_CONFIG_GAP_ANALYSIS_20260706.md` | Old vs. recommended config, gap-by-gap |
