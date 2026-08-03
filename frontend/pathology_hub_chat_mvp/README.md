# Pathology Hub Chat MVP

Local GPT-style chat UI for Pathology Hub. Retrieves evidence from the live backend via the **single supported operation** `POST /evidence/search`, then optionally synthesizes a grounded answer with OpenAI.

This workstream is separate from the curriculum provenance browser and from GPT Builder deployment.

## What it does

- Chat UI with message history, source selection, and citation cards
- Calls live Cloud Run `pathology-hub-v04` `/evidence/search` (via `pathology_backend.py`)
- Shows per-source result links (`source_url`, `figure_url`, `video_time_url`, etc.) when returned by the API
- Optional debug panel: request payloads, `source_status`, warnings (never API keys)
- **One Ask box** — no mode picker. The query is auto-routed to an internal shape: `topic_page` (entity / “what is…”), `compare_sources` (vs / difference), `visual` (show figures), `search_only` (“sources only”), or short `gpt_like`. Browse leaves still force `topic_page`.

## Keep local WSL in sync with cloud-agent edits

Cloud agents push to a feature branch; your WSL checkout does **not** auto-update. After an agent says it pushed:

```bash
cd /home/charlie/pathology-hub-dev
./frontend/pathology_hub_chat_mvp/scripts/sync_and_run_local.sh
# equivalent: pull cursor/topic-iterative-sse-layout-9231, kill old uvicorn, restart
```

Then hard-refresh the browser (Ctrl+Shift+R). Confirm the terminal shows
`BUILD=topic-iterative-sse-layout-9231 sha=<new>` matching the agent’s latest commit.

## Prerequisites

- Python 3.11+ (3.14 works with the bundled venv)
- `PATHOLOGY_HUB_API_KEY` or `HUB_API` in the environment (or `gcloud` access to Secret Manager `PATHOLOGY_HUB_API_KEY`)
- `OPENAI_API_KEY` for synthesis modes (`search_only` works without OpenAI)

Optional overrides:

- `PATHOLOGY_HUB_API_URL` — backend base URL (default: live Cloud Run v04)
- `OPENAI_MODEL` — default **`gpt-4o`** (see **Synthesis model A/B** below); override e.g. `OPENAI_MODEL=gpt-4.1-mini`
- `TOPIC_PAGE_ROOT_NARROW` — **on by default**; set to `0`/`false`/`off` to disable same-root filtering of textbooks/pathout/videos (WHO always kept, **except** on `Cyto_*` pages — see B9 below)
- `TOPIC_PAGE_LIVE_LITERATURE` — **on by default**; set to `0` to skip live Elsevier Scopus / PubMed / OncoKB on topic pages
- `TOPIC_PAGE_ITERATIVE` — **on by default**; multi-round retrieval (broad → gap-fill → literature deepen) with SSE progress via `POST /api/chat/stream`
- `TOPIC_PAGE_ITERATIVE_ROUNDS` — max rounds 1–3 (default `3`)
- `ELSEVIER_API_KEY`, `NCBI_API_KEY`, `ONCOKB_API_TOKEN` — optional env overrides; otherwise loaded from Secret Manager secrets `Elsevier`, `NCBI`, `OncoKB`
- `PORT` — local server port (default `8000`)

### Live literature (topic pages)

Topic pages call Elsevier Scopus + NCBI PubMed (+ OncoKB when gene symbols appear in the query) in parallel with hub RAG. Results become `literature` cards with DOI/PubMed links and feed **Key Literature** / **Molecular / Therapeutic** sections. This replaces the retired local journal FAISS index.

## Run locally

```bash
cd frontend/pathology_hub_chat_mvp
chmod +x scripts/run_local.sh
./scripts/run_local.sh
```

Open http://127.0.0.1:8000/

## Deploy HTTPS (Cloud Run)

Google-managed TLS on `https://*.run.app` — no custom cert required.

```bash
cd frontend/pathology_hub_chat_mvp
chmod +x scripts/deploy_cloud_run_https_v0_1.sh
./scripts/deploy_cloud_run_https_v0_1.sh
```

Defaults:

- Service: `pathology-hub-chat-mvp`
- Region: `us-central1`
- Project: `pathology-annotation-project`
- Secrets: `OPENAI` → `OPENAI_API_KEY`, `PATHOLOGY_HUB_API_KEY` → `PATHOLOGY_HUB_API_KEY`
- Public: `--allow-unauthenticated` (set `ALLOW_UNAUTHENTICATED=0` for private)

See `docs/DEPLOY_CHAT_MVP_HTTPS_CLOUD_RUN_v0_1.md`.

## API endpoints (local)

| Route | Purpose |
|-------|---------|
| `GET /` | Chat UI |
| `GET /api/health` | App + backend health, secret presence (no values); includes `ui_sources`, iterative/literature flags |
| `POST /api/chat` | Retrieve evidence + optional OpenAI answer (blocking) |
| `POST /api/chat/stream` | Same as `/api/chat` but SSE: `progress` events per retrieval round, then `result` |
| `POST /api/search` | Raw evidence only |
| `GET /api/openai_ping` | OpenAI connectivity smoke test |

## Tests

From repo root (no live API key required):

```bash
frontend/pathology_hub_chat_mvp/.venv/bin/python -m unittest \
  tests.test_pathology_hub_chat_mvp \
  tests.test_iterative_topic_retrieval \
  tests.test_literature_apis -v
```

Offline + optional live smoke:

```bash
cd frontend/pathology_hub_chat_mvp
./.venv/bin/python scripts/smoke_test_chat_mvp_v0_1.py          # TestClient only
./.venv/bin/python scripts/smoke_test_chat_mvp_v0_1.py --live # requires run_local.sh
```

## Topic-page prebuild (Phase 6)

With `./scripts/run_local.sh` running:

```bash
# Draw high-traffic sample (HN, Eye_Orbit, Breast, GU, GI)
python3 scripts/draw_high_traffic_sample_v0_1.py --per-root 3

# Batch prebuild (parallel workers, audit JSON)
python3 scripts/prebuild_topic_pages_pilot_v0_1.py \
  --sample outputs/chat_mvp_topic_prepop_v0_1/high_traffic_sample_v0_1.json \
  --parallel 2 \
  --audit-out outputs/chat_mvp_topic_prepop_v0_1/high_traffic_prebuild_audit_v0_1.json

# Explicit tags
python3 scripts/prebuild_topic_pages_pilot_v0_1.py \
  --tags "HN::Salivary_Gland::Benign_Tumor::Pleomorphic_Adenoma"
```

Other ops scripts: `root_narrow_ab_v0_1.py`, `model_ab_topic_synthesis_v0_1.py` (see README
sections above). Audits land under `outputs/chat_mvp_topic_prepop_v0_1/` (gitignored).

## Boundaries

- **One backend operation only:** `POST /evidence/search`
- Does not mutate GCS or change Cloud Run
- Does not claim a source is indexed/vectorized unless the live API returns results and `source_status`
- Not a substitute for clinical diagnosis

## Teaching session notes

Advanced (evidence sources) and **Export current page as JSON** live in a bottom stack under the chat panel so Browse topics are full-width. Topic pages also show an export button at the bottom of the page. Live journal papers come from Elsevier / PubMed / OncoKB (`literature`); the retired local `journals` FAISS corpus is not offered in the source checkboxes.

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
**Ask** is a single free-text box: entity names and “what is…” questions become topic pages
automatically; compare/visual/search-only phrasing selects those shapes without a dropdown.

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
comprehensive, structured, DDx-aware prompt is long.

### Synthesis model A/B (G16, measured 2026-07-11; superseded 2026-07-30)

Three fixed entities (Middle Ear SCC, GCT of Bone, Juvenile Granulosa Cell Tumor) were probed
with `scripts/model_ab_topic_synthesis_v0_1.py` (audit:
`outputs/chat_mvp_topic_prepop_v0_1/model_ab_topic_synthesis_v0_1.json`):

| `OPENAI_MODEL` | Avg total `/api/chat` time | All required sections present | Notes |
|---|---|---|---|
| `gpt-4.1-mini` | ~35s | yes | Longest answers (~5–6k chars); prior default |
| `gpt-4o-mini` | ~30s | yes | Shorter answers (~2.1–2.4k chars); not faster than mini here |
| `gpt-4o` | ~18s | yes | Fastest in this A/B; shorter but structurally complete — default 2026-07-11 through 2026-07-21 |

**2026-07-21 → 2026-07-29 regression:** a separate `OPENAI_TOPIC_PAGE_MODEL`/`gpt-5.6-luna`
default was introduced for `topic_page` synthesis only. `gpt_like` (free-text Ask), `compare_sources`,
`visual`, `html_teaching`, and `/api/compare` were never updated to match, so they silently kept
using `gpt-4o` — plus the Cloud Run deploy script hardcoded `OPENAI_MODEL=gpt-4o` as an env var,
which would have overridden any Python-level default change anyway.

**Current default (2026-07-30):** `gpt-5.6-luna` everywhere (`openai_synthesizer.DEFAULT_MODEL` ==
`TOPIC_PAGE_DEFAULT_MODEL`), and every `synthesize()` call site in `app.py` passes
`model=get_topic_page_model()` explicitly so chat/compare/visual/html_teaching can't drift back onto
an old default even if `OPENAI_MODEL` and `OPENAI_TOPIC_PAGE_MODEL` are later set to different
values. Override for a single local run with `OPENAI_MODEL=gpt-4.1-mini ./scripts/run_local.sh` (or
`OPENAI_TOPIC_PAGE_MODEL=...` — both now feed the same code paths). Re-run
`scripts/model_ab_topic_synthesis_v0_1.py` after prompt changes.

### Root-narrowed retrieval (B8)

**Default: on.** `TOPIC_PAGE_ROOT_NARROW` drops off-root textbooks/pathout/videos after retrieval while
keeping WHO + journals. Disable with `TOPIC_PAGE_ROOT_NARROW=0` if breadth matters or a thin root
starves results. Measured A/B (`scripts/root_narrow_ab_v0_1.py`):

- **HN Pleomorphic Adenoma:** 67 → 52 cards (off-root HN noise trimmed; not starved)
- **Eye choroidal melanoma:** 53 → 24 cards (still usable; watch thin roots)
- **Middle Ear SCC:** 59 → 42 cards

Use root narrow when off-root textbook/video noise dominates; disable (`TOPIC_PAGE_ROOT_NARROW=0`)
for thin roots (e.g. some Eye pages dropped 53→24 cards) or when breadth matters.

**Cyto strictness (B9, added 2026-07-26):** `Cyto_*` pages (e.g. `Cyto_Thyroid`) apply a stricter
variant of the same filter — see `is_cyto_root_token`/`filter_cards_by_page_root` in
`pathology_backend.py`. Root cause: WHO entity cards never carry a `primary_tag` (confirmed across
every captured WHO response in `audits/**/*.json` — always `None`), so the ordinary B8 policy of
"keep WHO regardless of root" showed the generic/histologic WHO write-up for a diagnosis on its
`Cyto_*` page too, purely because the diagnosis text/entity is shared with the non-cyto surgical
entity of the same name — reported by the user as cyto pages "covering non cyto things ... cuz of
using the same diagnosis". For `Cyto_*` pages only: WHO is added to the root-filterable source set,
and cards/figures with no resolvable root (previously kept by default) are now dropped instead of
kept, since only content with a confirmed matching `Cyto_*` root can be shown. Textbook/pathout/
video content was already reliably tagged with a resolvable `Cyto_*` vs non-cyto `primary_tag` in
every sampled live response, so this mainly affects WHO; non-cyto pages are completely unaffected
(same behavior as before). Live literature (`journals`, fetched separately via Elsevier/PubMed/
OncoKB) is unscoped either way — it never carries repo-tag metadata to filter on.

**Cyto strictness fix (2026-08-01):** B9 as originally written silently dropped *every* WHO/
textbook/pathout/video card on any Browse-nav-derived `Cyto_*` content-spec page (`ABPathSpec::
cyto::…` tags — the Browse nav's own root id for these is always the bare generic `"cyto"`, never
a specific organ, since content-spec entities aren't individually mapped to a `Cyto_<Organ>`
identifier the way WHO/PathOut source tags are — see `CYTO_SYSTEM_*` in
`build_browse_tag_index_who_abpath_spec_v0_1.py`, which only reorganizes Browse *navigation*
bucketing, not the tag itself). Strict-cyto root matching required an *exact* organ-token match,
and the bare `"cyto"` target never exactly matches any organ-specific card root (`"cytogyn"`,
`"cytothyroid"`, …) — so every card was dropped, which is strictly worse than no filtering at all.
Fixed two ways in `pathology_backend.py`: (1) `is_cyto_root_token` now returns `False` for the bare
`"cyto"` token — WHO stays in the ordinary (non-root-filterable) B8 policy on these pages, since B9
strictness with no organ to scope to has no useful signal; (2) `_root_matches_page` now treats any
organ-specific `"cyto*"` root as on-topic when the *target* itself is bare `"cyto"` — so
textbook/pathout/video content across the whole cyto family is shown (not narrowed to one organ,
but no longer empty, and never leaking in non-cyto surgical-pathology content of the same
diagnosis name, which was B9's original goal). **Known limitation:** content-spec-derived cyto
pages still cannot be narrowed to one specific organ system (e.g. a GYN cytology content-spec page
may still show Breast/Thyroid cyto textbook content) — true organ-level precision on these pages
would require mapping each content-spec entity to a `Cyto_<Organ>` identifier, which content-spec
data does not carry. Pages opened from a real WHO/PathOut `Cyto_<Organ>` tag (e.g.
`Cyto_GYN::Squamous::…`) were already organ-scoped correctly before this fix and are unaffected.

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

**Textbook retrieval degrades under concurrent prebuild load (found 2026-08-03):** BST prebuilds
run at `--parallel 3` came back with `source_status.textbooks == "not_requested"` on ~93% of the
189 leaves (only WHO/literature populated), even though `Enzinger and Weiss's Soft Tissue Tumors`
(`softtissue_enzinger`), `Dorfman and Czerniak's Bone Tumors` (`bone_dorfman`), and the AFIP-style
`Horvai` BST atlas (`bst_horvai`) — plus `bone_atlas`, `bone_pattern`, `softtissue_pattern` — are
all indexed in the same `textbooks_lean` corpus as every other specialty (confirmed against the
backend's own manifest and source PDFs; not a missing-corpus issue). `source_status` is set purely
by the pathology-hub-v04 backend's own `/evidence/search` response body — this repo's code
(`merge_outcomes` in `pathology_backend.py`) only reads it through, never sets it — so this is a
backend-side effect of concurrent load, not a client bug. Confirmed by re-running the same BST
leaves at `--parallel 2` immediately after the `--parallel 3` batch finished (backend otherwise
idle): `textbooks`/`pathout` came back `"ok"` on 189/189 pages, per-page latency dropped from
~150-200s to ~25-45s, and card counts nearly doubled (4,401 → 6,367 total cards across the BST
set). **Mitigation:** keep `prebuild_topic_pages_pilot_v0_1.py --parallel` at 2 or lower for any
future large batch prebuild run against this backend; higher concurrency silently degrades the
expensive textbook/pathout hybrid search while cheap WHO lookups keep returning `"ok"`, so a
skimmed audit that only checks `n_ok`/`n_failed` (both look fine) won't catch it — check
`retrieval_debug_summary.source_status` per source, not just overall success.

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
