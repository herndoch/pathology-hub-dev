# Topic page quality burn (v0_1)

Offline quality tooling for Chat MVP prebuilt topic pages.

## Scripts

- `frontend/pathology_hub_chat_mvp/scripts/score_topic_page_quality_v0_1.py` — free structural rubric
- `frontend/pathology_hub_chat_mvp/scripts/run_topic_page_quality_burn_v0_1.py` — structural + multi-model LLM reviews + repair queue
- `frontend/pathology_hub_chat_mvp/scripts/pathologist_review_topic_pages_v0_1.py` — advisory pathologist critique sidecars
- `frontend/pathology_hub_chat_mvp/scripts/repair_topic_pages_from_quality_queue_v0_1.py` — rebuild worst queue items

## Outputs

- Per-page sidecars (gitignored under `outputs/chat_mvp_topic_prepop_v0_1/pages/`):
  - `*.quality.json` — structural score / flags
  - `*.review.json` — pathologist LLM verdict
  - `*.review2.json` — hostile-editor second pass when first pass was bad
- Summary audits copied here for git tracking when a burn runs.

## Verdicts

`ready_for_human_review` | `needs_fixes` | `blocked_thin_evidence`

LLM reviews are advisory only — not human pathologist sign-off.
