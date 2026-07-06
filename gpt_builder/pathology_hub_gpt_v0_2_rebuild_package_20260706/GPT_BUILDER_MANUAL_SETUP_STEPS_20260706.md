# GPT Builder Manual Setup Steps — v0_2 — 2026-07-06

**Every step below must be performed manually by Charlie in the GPT Builder UI.
This session has no GPT Builder access and did not perform any of these steps.**

## Recommended approach: clone-test-first (see `GPT_BUILDER_CONFIG_SUMMARY_20260706.md` for reasoning)

### Step 1 — Duplicate the GPT

1. Open "Pathology Hub GPT — Search Only v1.00" in GPT Builder.
2. Use the GPT's context menu / editor options to **Duplicate** it, creating a
   private, unpublished copy. Work only in the copy for steps 2-6.

### Step 2 — Update Instructions

1. Open the "Configure" tab of the duplicated GPT.
2. Replace the entire Instructions field content with the text in
   `GPT_INSTRUCTIONS_PATHOLOGY_HUB_V0_2_PASTE_READY.txt` (this package). It is a
   full replacement, not a partial edit — the new text is a superset of the
   existing v1.5.9 instructions plus the v0_2-specific additions.
3. Optionally update the Description field using the suggested text in
   `GPT_NAME_DESCRIPTION_CAPABILITIES_20260706.md` (this package).

### Step 3 — Update Knowledge panel

1. Remove any historical/stale files per `GPT_KNOWLEDGE_UPLOAD_MANIFEST_20260706.md`
   (this package) — files dated 20260704 or earlier, or superseded API contract/
   OpenAPI reference documents.
2. Upload the 7 recommended files listed in that same manifest (from the
   `project_sources/updates/20260705/` and `project_sources/updates/20260706/`
   packages in the repo).

### Step 4 — Confirm/decide on Action schema reimport

1. Read `GPT_ACTION_SCHEMA_DECISION_20260706.md` (this package).
2. **Default recommendation: do nothing — the existing Action definition already
   works correctly with v0_2** (verified: same server URL, same operationId, schema
   already permits additional response properties).
3. **Only if** Charlie wants `query_expansion_applied` explicitly self-documented in
   the schema: open the Action's "Edit" screen in GPT Builder and replace the
   schema with the contents of `GPT_ACTION_OPENAPI_CURRENT_RECOMMENDED.yaml` (this
   package). Confirm the server URL field still shows
   `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app` and the operationId still
   shows `searchEvidence` after the paste, before saving.
4. Confirm the Action's authentication is still configured as API Key, header
   `X-API-Key` (unchanged) — do not re-enter the key value in this session's
   presence; this is a value only Charlie should handle directly in GPT Builder.

### Step 5 — Save and enter Preview

1. **Click Update/Save in GPT Builder.** This is a manual UI action that must be
   performed after every change above — nothing in steps 2-4 takes effect until
   saved.
2. Open the Preview pane for the duplicated GPT.

### Step 6 — Run the QA prompts

1. Work through every prompt in `GPT_PREVIEW_QA_PROMPTS_V0_2_20260706.md` (this
   package) against the Preview pane.
2. Score each using `GPT_PREVIEW_SCORING_RUBRIC_V0_2_20260706.md` (this package).
3. Any FAIL should be treated as an instructions-text issue to fix in the
   duplicate and re-test — do not promote until all prompts pass.

### Step 7 — Promote

Once all QA prompts pass on the duplicate:

- **Option A:** Copy the validated Instructions text and Knowledge file list from
  the duplicate into the original live "Pathology Hub GPT — Search Only v1.00" and
  click Update/Save there.
- **Option B:** If Charlie's sharing/publishing setup makes it simpler, publish the
  duplicate itself and redirect any saved links/bookmarks to it, retiring the
  original. (This session cannot see Charlie's actual sharing configuration to
  recommend definitively between A and B — either is safe given the content is
  identical and already QA-passed.)
- **Do not delete the original GPT** during this process, in case a rollback to the
  prior instructions/Knowledge state is ever needed.

## If Charlie instead chooses to update the live GPT directly (skip cloning)

Follow steps 2-6 directly against the live "Pathology Hub GPT — Search Only v1.00"
instead of a duplicate, understanding this carries the direct-edit risk discussed in
`GPT_BUILDER_CONFIG_SUMMARY_20260706.md`. **Step 5's Save/Update click and Step 6's
QA pass are still mandatory** even in this path — do not skip QA just because a
duplicate wasn't used.
