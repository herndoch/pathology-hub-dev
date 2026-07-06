# GPT Knowledge Upload Manifest — v0_2 — 2026-07-06

**Note: GPT Builder's "Knowledge" panel is distinct from "ChatGPT Project Sources."**
This manifest is specifically for GPT Builder's own Knowledge panel (files the GPT
can retrieve from directly), not the Project Sources upload discussed in the
20260705/20260706 project-source packages. Do not conflate the two.

## Recommended: curated subset to upload (canonical/current)

| File | Repo path | Why |
|---|---|---|
| `README_PROJECT_UPDATE_PACKAGE_20260705_v0_2.md` | `project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/` | Orients the GPT (if it ever reads Knowledge for self-context) to current v0_2 production state |
| `CURRENT_MASTER_SPINE_20260705_v0_2_ADDENDUM.md` | same folder, `docs/` | Canonical current-state summary |
| `API_CONTRACT_20260705_v0_2_ADDENDUM.md` | same folder, `docs/` | Exact request/response contract detail |
| `GPT_INSTRUCTIONS_DELTA_V0_2_20260705.md` | same folder, `docs/` | Explains what changed and mandatory guardrails |
| `README_PROJECT_UPDATE_PACKAGE_20260706_v0_2_COLD_START_RUNTIME_CORRECTION.md` | `project_sources/updates/20260706/pathology_hub_v0_2_cold_start_runtime_correction_20260706/` | Corrects the live-revision detail (00029-rnt, not 00028-guf) |
| `CURRENT_MASTER_SPINE_20260706_v0_2_COLD_START_ADDENDUM.md` | same folder, `docs/` | Current corrected state |
| `GPT_INSTRUCTIONS_DELTA_V0_2_COLD_START_20260706.md` | same folder, `docs/` | Confirms no GPT-visible change from the cold-start fix |

**Total: 7 files.** All are small, text-only, addendum-style documents — appropriate
size and content for a Knowledge panel meant to give the GPT (or a human reviewing
the GPT's configuration) accurate current-state context.

## Explicitly EXCLUDE from Knowledge panel

- Any raw audit JSON/CSV files (`audits/`, `benchmark_v0_2/staging_run_cycle_1/`) —
  far too large and not meant for GPT retrieval; these are engineering evidence, not
  user-facing knowledge.
- The release ZIP (`pathology_hub_v0_2_production_release_20260705.zip`) — a
  packaging artifact, not a knowledge document.
- Any `SHA256SUMS_*.txt` file — pure checksums, no informational value to the GPT.
- `MANIFEST_V0_2_PRODUCTION_RELEASE_20260705.csv` — an internal file listing, not
  knowledge content.
- `HANDOFF_BACKEND_API_EVIDENCE_SEARCH_RELIABILITY_V0_2_PROD_20260705.md` and its
  20260706 counterpart — these are engineering handoff docs (heavy on Cloud Run
  commands, revision IDs, internal file paths) intended for the next engineer, not
  for the GPT's own retrieval context. Including them is not harmful, but they add
  no value the GPT would ever need to answer a user's pathology question and add
  Knowledge-panel clutter.
- `DECISIONS_LOG_*_ADDENDUM.md` and `WORKSTREAM_STATUS_*.md` files — internal
  process records, not useful for the GPT's actual task.

## Mark as HISTORICAL / STALE — recommend removal (per Charlie's report of the
current Knowledge panel contents)

Charlie reported the Knowledge panel "appears to contain only older GPT
builder/API contract files." Based on file naming conventions already present in
this repo, the most likely stale candidates are any files corresponding to:

- `API_CONTRACT_20260704_v1_5_9_curriculum.md` / `_FINAL.md` (repo root `docs/`) —
  **superseded** by `API_CONTRACT_20260705_v0_2_ADDENDUM.md`
- Any `openapi_pathology_hub_unified_searchEvidence_v1_5_8*.yaml` or
  `v1_5_9*.yaml` files — **superseded** by the current recommended schema in this
  package (`GPT_ACTION_OPENAPI_CURRENT_RECOMMENDED.yaml`), though note the Action's
  actual OpenAPI definition lives in the Action config, not Knowledge — if any
  OpenAPI YAML was uploaded to Knowledge as a *reference document* (not the live
  Action schema itself), it should be replaced with the current one to avoid the
  GPT reading stale contract details from Knowledge that contradict the live Action.
- `GPT_INSTRUCTIONS_CURRICULUM_MAP_v1_5_9_DRAFT.md` (repo root `docs/`) — if this
  was ever uploaded to Knowledge, it reflects a **draft, pre-v0_2** state and should
  be removed or replaced with the current addendum docs above.

**This session cannot see the actual current Knowledge panel file list** (no GPT
Builder access) — the above is a best-effort inference from repo file-naming
history matching Charlie's description ("older GPT builder/API contract files").
Charlie should open the Knowledge panel and remove anything dated 20260704 or
earlier once the 7 recommended files above are uploaded, using his own judgment on
exact file names present.

## Format note

If GPT Builder Knowledge requires a specific file type (e.g. `.txt`/`.pdf` only,
not `.md`), the 7 recommended files can be copy-pasted into plain `.txt` versions
without any content loss — they contain no special Markdown formatting beyond
headers and tables that would be lost in translation to plaintext.
