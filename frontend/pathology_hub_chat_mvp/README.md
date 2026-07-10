# Pathology Hub Chat MVP

Local GPT-style chat UI for Pathology Hub. Retrieves evidence from the live backend via the **single supported operation** `POST /evidence/search`, then optionally synthesizes a grounded answer with OpenAI.

This workstream is separate from the curriculum provenance browser and from GPT Builder deployment.

## What it does

- Chat UI with message history, source selection, and citation cards
- Calls live Cloud Run `pathology-hub-v04` `/evidence/search` (via `pathology_backend.py`)
- Shows per-source result links (`source_url`, `figure_url`, `video_time_url`, etc.) when returned by the API
- Optional debug panel: request payloads, `source_status`, warnings (never API keys)
- Modes: `gpt_like` (default), `search_only`, `compare_sources`, `visual`, `html_teaching`, `topic_page` (preview — see below)

## Prerequisites

- Python 3.11+ (3.14 works with the bundled venv)
- `PATHOLOGY_HUB_API_KEY` or `HUB_API` in the environment (or `gcloud` access to Secret Manager `PATHOLOGY_HUB_API_KEY`)
- `OPENAI_API_KEY` for synthesis modes (`search_only` works without OpenAI)

Optional overrides:

- `PATHOLOGY_HUB_API_URL` — backend base URL (default: live Cloud Run v04)
- `OPENAI_MODEL` — default `gpt-4.1-mini`
- `PORT` — local server port (default `8000`)

## Run locally

```bash
cd frontend/pathology_hub_chat_mvp
chmod +x scripts/run_local.sh
./scripts/run_local.sh
```

Open http://127.0.0.1:8000/

## API endpoints (local)

| Route | Purpose |
|-------|---------|
| `GET /` | Chat UI |
| `GET /api/health` | App + backend health, secret presence (no values) |
| `POST /api/chat` | Retrieve evidence + optional OpenAI answer |
| `POST /api/search` | Raw evidence only |
| `GET /api/openai_ping` | OpenAI connectivity smoke test |

## Tests

From repo root (no live API key required):

```bash
frontend/pathology_hub_chat_mvp/.venv/bin/python -m unittest tests.test_pathology_hub_chat_mvp -v
```

## Boundaries

- **One backend operation only:** `POST /evidence/search`
- Does not mutate GCS or change Cloud Run
- Does not claim a source is indexed/vectorized unless the live API returns results and `source_status`
- Not a substitute for clinical diagnosis

## Teaching session notes

The right sidebar includes a collapsible **Teaching session notes** panel for capturing teaching points or session follow-ups. Content auto-saves to browser `localStorage` (`pathology_hub_teaching_session_notes`; migrates from legacy `pathology_hub_experiment_notes`) and survives refresh. Use **Copy notes** or **Export markdown** to share.

## UI features

- Markdown rendering for synthesized answers
- Human-readable source labels and link text
- Inline citation thumbnails with lightbox preview for page/figure images
- Retrieval relevance warnings when top hits may not match query terms
- Prominent link when HTML teaching mode generates a hosted page

## Topic page mode (preview — in progress)

`topic_page` is a new `/api/chat` mode for an ExpertPath-style reference page on ONE named
diagnosis/entity (e.g. type `BAP1-inactivated melanocytoma` and select **Topic page** from
the mode dropdown). The backend/prompt side is complete:

- `prompts.topic_page_system_prompt()` instructs the model to answer strictly under a fixed,
  ordered set of markdown headers — `## Key Facts`, `## Terminology`, `## Etiology/Pathogenesis`,
  `## Clinical Issues`, `## Microscopic`, `## Ancillary Tests`, `## Differential Diagnosis` —
  every time, even writing "Not covered in retrieved evidence." under a header instead of
  omitting it. Inherits all `BASE_GROUNDING_RULES` (no invented facts/URLs/differentials).
- `app.py` `_apply_figure_defaults` forces `include_figures=True`/`max_figures=8` for this mode
  so a figure gallery is always requested.
- Currently renders through the **same generic markdown renderer** as other modes (the `##`
  headers become subheadings, bullets/tables render normally) — there is **no dedicated
  Key-Facts-box + dark-section-bar + image-gallery layout yet**, and **no nested
  category → subcategory → entity browse tree**, and **no clickable Differential Diagnosis
  cross-links**. Those are the next milestone; see `docs/ACTIVE_CONTEXT.md`.

## v2 gaps

- Full ExpertPath-style nested "Browse" tree (home tile grid → subcategory list → leaf entity
  list) with a dedicated topic-page layout and clickable Differential Diagnosis cross-links —
  designed but not yet built (see Topic page mode above)
- Link citations into the curriculum provenance browser by `record_id`
- Streaming answers and conversation memory across turns
- Smarter default source routing (tag-aware API when live)
- GPT Builder / Actions packaging and hosted deployment
- Figure quality-flag awareness in the UI
