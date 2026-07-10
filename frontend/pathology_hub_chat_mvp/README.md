# Pathology Hub Chat MVP

Local GPT-style chat UI for Pathology Hub. Retrieves evidence from the live backend via the **single supported operation** `POST /evidence/search`, then optionally synthesizes a grounded answer with OpenAI.

This workstream is separate from the curriculum provenance browser and from GPT Builder deployment.

## What it does

- Chat UI with message history, source selection, and citation cards
- Calls live Cloud Run `pathology-hub-v04` `/evidence/search` (via `pathology_backend.py`)
- Shows per-source result links (`source_url`, `figure_url`, `video_time_url`, etc.) when returned by the API
- Optional debug panel: request payloads, `source_status`, warnings (never API keys)
- Modes: `gpt_like` (default), `search_only`, `compare_sources`, `visual`, `html_teaching`, `topic_page` (see Browse tab section below)

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

## Browse tab / Topic page mode

The **Browse** tab (default landing view) is an ExpertPath-style nested reference tree: a home
grid of ~17 organ-system tiles → a plain chevron list of subcategories → a chevron list of real
diagnosis entities. Clicking a leaf entity calls `/api/chat` with `mode: "topic_page"` fresh every
time (never cached) and renders a dedicated layout: a Key Facts box + right-side figure gallery on
top, then dark-bar sections below (Terminology, Etiology/Pathogenesis, Clinical Issues,
Microscopic, Ancillary Tests, Differential Diagnosis). Differential Diagnosis entries are
fuzzy-matched against the same static taxonomy and rendered as clickable cross-links to that
entity's own fresh topic page when confident; unmatched entries stay plain text (never a fabricated
link). The taxonomy (`BROWSE_TAXONOMY` in `app.js`) is a self-contained, editorially curated static
structure — not read from the curriculum provenance browser's SQLite (different workstream) — and
every navigation still goes through the single supported `POST /evidence/search` operation. The
**Ask** tab keeps the original free-text chat flow (mode dropdown includes `topic_page` too, for
typing an entity name directly).

`topic_page` requests always use the **full source set** (`textbooks`, `who`, `pathout`,
`journals`, `lectures`, `videos` — never `curriculum`, which is navigation-only), enforced
server-side in `app.py` regardless of the sidebar's checked sources, since a topic page is meant to
be comprehensive. Per-source result lists are also round-robin re-ranked by `source_id`
(`diversify_by_source_id` in `pathology_backend.py`) so one dominant textbook doesn't crowd out
other textbooks covering the same topic — verified live: a real "ovarian high-grade serous
carcinoma" probe returned 3 distinct textbook `source_id`s correctly interleaved. **Known
limitation:** the lecture/video corpus's `source_id` field is a single constant across the whole
corpus (not per-lecture), so diversification currently has no effect there — a future fix would
need a more granular per-lecture identifier from the backend.

Retrieval across multiple sources is parallelized (`ThreadPoolExecutor` in
`pathology_backend.staged_retrieve` — still one backend operation, just fanned out concurrently
instead of one-at-a-time). Measured live: a 6-source topic-page probe's retrieval stage completed
in ~17s (bounded by the single slowest source) instead of the ~22s a sequential sum of the same
calls would take — and that gap widens further whenever no single source is a severe outlier.
OpenAI synthesis, not retrieval, is now the dominant cost for `topic_page` specifically (the
6-source ovarian-HGSC probe was ~52s total: ~17s retrieval, ~35s synthesis) because the
comprehensive, structured, DDx-aware prompt is long. We did not swap the default model for a
faster one — that's a real lever, but we could not validate a faster model's grounding compliance
within this session, and this mode's whole purpose is comprehensive correctness, so it's left as a
documented option (`OPENAI_MODEL` env var) rather than a default change.

**Known limitation — journals:** `/api/health`'s `journal_vector_manifest_summary.api_exposed_note`
says journal vector retrieval "requires a v04.5 patch" and isn't exposed yet — but a live probe
shows this note is stale: `source_status.journals == "ok"` and real article metadata (titles,
DOIs) come back today. However, roughly half of returned journal cards carry no `source_url` at
all (nothing to cite), and the ones that do point to Elsevier/`modernpathology.org`, which sit
behind Cloudflare bot-protection that returned 403 to every automated request we tried from this
dev sandbox — including a control request to `pathologyoutlines.com`, which is known-good in this
app, so we could not distinguish "dead link" from "bot-blocked sandbox" with any live check. We
deliberately did **not** add a server-side HEAD-check filter for this: the same check running from
Cloud Run's egress IP could just as easily get bot-challenged and incorrectly hide valid citations.
Journals stay in the default `topic_page` source set since retrieval itself is proven live; link
resolution for end users is unverified either way, not disproven.

## Citation tags

Citation cards (`renderCitations` in `app.js`, used by both the normal chat citation list and the
topic-page reference list) show a small muted tag chip from the card's `primary_tag` or first
`candidate_tags` entry when present — never fabricated, and skipped entirely for missing/blank tags
or the literal `__UNMAPPED__` placeholder some PathOut rows carry.

## Color theme

Light, Google-Sans-inspired palette (`:root` in `style.css`): white/light-gray surfaces, Google blue
accent (`#1a73e8`), dark-gray body text — replacing the original dark theme. Topic-page section
bars intentionally stay dark (`#202124`) to match ExpertPath's own dark navy section bars on a
light page; organ-system browse tiles keep their own bold per-category gradients (unrelated to the
overall light/dark surface theme) with white text for contrast.

## v2 gaps

- Link citations into the curriculum provenance browser by `record_id`
- Streaming answers and conversation memory across turns
- Per-lecture diversification (blocked on a more granular backend `source_id`/`lecture_id` for
  lecture/video results — see Browse tab section above)
- GPT Builder / Actions packaging and hosted deployment
- Figure quality-flag awareness in the UI
