# Active Context

Last updated: 2026-07-26

## Product decision (current — corrected 2026-07-26)

**Browse nav = combined, deduped ABPath + WHO topic tags; PathOut is retrieval/citation-only,
not a nav source.** Live since the 2026-07-11 Browse UX overhaul
(`frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py`, rules A1–A5): ABPath
tags are primary and deduped by casefolded full tag path (one leaf per root+display label,
ABPath spelling wins on overlap); WHO tags are ingested as a gap-filler overlay only (tags not
already covered by ABPath under the same label). Confirmed live in
`frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json`
(`schema_version: browse_tag_index_v0_2`, generated `2026-07-11T14:44:00Z`): **7,692 leaves / 15
roots** — 5,759 ABPath-only, 1,765 WHO-only (genuine ABPath gaps WHO filled), 168 overlap
(`"both"`). `dedupe_rules.pathout_nav` is explicitly `false`. Cytopathology stays its own
top-level root from `Cyto_*` tag roots.

Browse IA plan: `docs/PLAN_CHAT_MVP_BROWSE_EXPERTPATH_INSPIRED_v0_1.md`.  
Prepop pilot plan: `docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md` +  
`docs/HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md` — **pilot complete, see below**.

<details>
<summary>Superseded (2026-07-10 decision — kept for history, do not follow)</summary>

**Product decision (locked 2026-07-10, superseded 2026-07-11):** Browse nav = combined,
deduped ABPath + PathOut topic tags (not ABPath-only; not `cyto_*` book folders). PathOut may
cover histo/entity pages ABPath misses. Books remain retrieval sources only.

This was superseded the next day by the Browse UX overhaul (A1: "Browse nav = WHO + ABPath
only, no PathOut leaves") to keep PathOut strictly a retrieval/citation source per the
workstream-separation rule in `AGENTS.md`. This section had gone uncorrected in this doc for two
weeks despite the live index already reflecting the newer rule — reconciled 2026-07-26.

</details>

## Current task (local WSL agent — cyto retrieval leakage fix, 2026-07-26 night)

**Fix: cyto topic pages no longer show non-cyto content that shares a diagnosis label — offline
tests only, NOT confirmed live in a browser this session.** User report (verbatim): "the cyto tags
should prob only follow abpath cuz like cyto pages are covering non cyto things when they populate
cuz of using the same diagnosis."

**Root cause:** Topic pages already had a B8 "root-narrow" post-retrieval filter
(`page_root_from_tag`/`filter_cards_by_page_root`/`filter_figures_by_page_root` in
`frontend/pathology_hub_chat_mvp/pathology_backend.py`, previously lines 702–751) that drops
off-root textbook/pathout/video cards after retrieval — and it turns out to work correctly for
those three sources: every sampled live textbook/pathout/video card in this repo's `audits/**/*.json`
(65/65, 60/60, 35/35) carries a resolvable `primary_tag` or organ-prefixed `source_id`, e.g.
`Cyto_Thyroid::Malignant::...` vs plain `Thyroid::...`, so the existing root filter already tells
these apart correctly. The actual leak is **WHO**, which B8 deliberately always kept "regardless of
root" — and every WHO card sampled across this repo (`who_results` in every `audits/**/*.json` that
has any) carries `primary_tag: None`. WHO entity write-ups are generic diagnosis/classification
content (largely histologic/surgical in framing) with no cyto-vs-histo distinction at all, so the
"always keep WHO" policy meant the general WHO write-up for a diagnosis (e.g. "Papillary thyroid
carcinoma") showed up unconditionally on its `Cyto_Thyroid` page too, purely because the diagnosis
text/entity is shared with the non-cyto surgical entity of the same name — i.e. exactly the
diagnosis-driven leakage the user described. (Live literature/`journals` cards are fetched
separately via Elsevier/PubMed/OncoKB free-text search and were left out of scope — they carry no
repo tag metadata to filter on either way, same as before.)

**Fix (B9 cyto scoping, additive — zero behavior change for non-cyto pages):**
`frontend/pathology_hub_chat_mvp/pathology_backend.py`:
- New `is_cyto_root_token()` (~line 708) — true for any normalized root token derived from a
  `Cyto_*` ABPath tag root (e.g. `Cyto_Thyroid` → `cytothyroid`).
- New `_GENERIC_CYTO_SOURCE_TOKEN`/`_root_matches_page()` (~lines 722–735) — cyto textbooks/atlases
  (e.g. `cyto_cibas`, `cyto_comprehensive_part_two`) span every cyto organ in one book; only the
  per-chunk `primary_tag` carries the specific `Cyto_<Organ>` root, and figures never carry
  `primary_tag` at all (confirmed: 0/5 sampled figures have it) — only `source_id`. So the
  `source_id`-prefix fallback can only ever resolve cyto content to the generic `"cyto"` bucket,
  never a specific organ; `_root_matches_page` treats that generic bucket as on-topic for **any**
  `Cyto_*` page (not the wrong-organ rejection it would otherwise be).
- `filter_cards_by_page_root()` (~line 738) and `filter_figures_by_page_root()` (~line 780): when
  the page root is cyto-rooted, `who` is added to the filterable-source set, and the previous
  "unknown root → keep" fallback flips to "unknown root → drop" (for cards: textbooks/pathout/
  videos/who; for figures: any figure with no `source_id` at all) — i.e. cyto pages now require a
  *confirmed* on-root (or generic-cyto) tag rather than being shown by default. Non-cyto pages take
  the exact same code path as before B9 and are provably unaffected (see tests below).
- `frontend/pathology_hub_chat_mvp/README.md`: added a "Cyto strictness (B9)" paragraph under the
  existing "Root-narrowed retrieval (B8)" section documenting this.

**Test coverage added** (`tests/test_pathology_hub_chat_mvp.py`, `TestRootNarrowFilter`, new
imports `filter_figures_by_page_root`/`is_cyto_root_token`): `test_is_cyto_root_token`,
`test_cyto_page_drops_generic_who_card_for_same_diagnosis` (the core regression case — WHO card
dropped, cyto textbook/pathout kept, non-cyto textbook dropped, journals untouched),
`test_non_cyto_page_still_keeps_who_regardless_of_root` (proves zero regression for ordinary
pages), `test_cyto_page_drops_unresolvable_root_textbook_pathout_cards`,
`test_cyto_page_keeps_generic_cyto_sourced_card_missing_primary_tag`,
`test_filter_figures_by_page_root_drops_off_root_keeps_generic_cyto_on_cyto_pages`,
`test_filter_figures_by_page_root_keeps_unresolvable_on_non_cyto_pages`.

**Verification status: offline only.** Full suite green, 62/62 (`python -m unittest
tests.test_pathology_hub_chat_mvp -v` from repo root using
`frontend/pathology_hub_chat_mvp/.venv`), plus
`frontend/pathology_hub_chat_mvp/scripts/smoke_test_chat_mvp_v0_1.py` still green (`root_narrow=True`
in `/api/health`). Could not start the local server to hit the live backend from this sandboxed
shell (network is isolated even after `set -a && source .env`/`run_local.sh` — the already-running
dev server from the user's own terminal, PID 203045, is bound to `127.0.0.1:8000` in a different
network namespace this agent's shell cannot reach: `curl` to it here returns "Connection refused"
even with `full_network`/`all` permission attempts). **Not confirmed live in a browser.** User
should manually verify: open Browse → Cytopathology → Thyroid → a papillary/medullary/etc. thyroid
carcinoma leaf topic page, and confirm the WHO reference card (if previously visible) either
disappears or is replaced by nothing-from-WHO, while cyto-specific textbook/pathout/lecture-figure
content for that same leaf still appears unchanged. Also spot-check a **non-cyto** page (e.g. any
plain `Thyroid` or `Breast` leaf) still shows its WHO card as before, to confirm no regression.

## Current task (local WSL agent — session handoff, 2026-07-26 evening)

**Chat MVP shallow-answers / UX cleanup pass — uncommitted, mostly offline-verified only.**
Branch `cursor/topic-live-literature-apis-9231`, working tree dirty (not committed — user did
not ask for a commit). Touched files: `frontend/pathology_hub_chat_mvp/app.py`,
`literature_apis.py`, `openai_synthesizer.py`, `static/app.js`, `static/index.html`,
`static/style.css`, `tests/test_pathology_hub_chat_mvp.py`, this doc.

Chain of user reports → fixes this session:

1. **OpenAI 401** — stale key in local `.env`. Fix: removed `OPENAI_API_KEY` /
   `PATHOLOGY_HUB_API_KEY` (and `ELSEVIER_API_KEY`/`NCBI_API_KEY`/`ONCOKB_API_TOKEN` if present)
   from `.env` so the app falls back to GCP Secret Manager (user confirmed GCS keys are the
   current ones). **User must restart `run_local.sh` with `.env` re-sourced for this to take
   effect** — terminal 2 shows this restart was in progress when context ran out; not confirmed
   healthy post-restart.
2. **Topic pages shallow despite rich retrieval** — root cause:
   `openai_synthesizer._compact_evidence_json` hard-capped evidence JSON at 60k chars
   (`sort_keys=True` meant alphabetically-late sources like WHO/textbooks/videos got cut first).
   Fix: raised `_EVIDENCE_JSON_CHAR_CAP` to 350k in `openai_synthesizer.py`; `synthesize()` /
   `SynthesisResult` now report `evidence_truncated` + `evidence_char_len` so truncation is
   visible in the debug payload instead of silent.
3. **`gpt-5.6-luna` never actually used for topic pages** — `_answer_topic_page` in `app.py`
   wasn't passing `get_topic_page_model()`'s result through; fixed the wiring, and
   `topic_page_model` is now exposed in `/api/health`.
4. **Chat not showing pics** — figures were only fetched by default for queries with "visual"
   keywords. Fixed `_apply_figure_defaults` (`app.py`) + `buildPayload` (`app.js`) to request a
   modest figure budget (4, up to 8 for visual-sounding queries) by default for `gpt_like` /
   `compare_sources` modes.
5. **No left/right modal arrows for inline body images** — `bindPreviewHandlers` gallery
   detector only matched dedicated gallery grids. Broadened it to include
   `.topic-section-body` / `.topic-key-facts` so inline figures are part of the navigable
   gallery too.
6. **Topic-page display caps way below backend retrieval caps** — client capped citations at 20
   / figures at 16 while backend retrieves up to 120 cards / 40 figures. Raised `maxShown` to 80
   / 40 in `renderTopicPageResult`, `filterByQueryRelevance`, `renderTopicGallery`; also split
   the filter note into "off-topic" vs "overflowed but relevant" instead of one misleading
   message.
7. **Literature = recency-only text matching** — Scopus search forced `sort=-coverDate`. Removed
   that sort (relevance-ranked instead) in `literature_apis.py`; added explicit
   `sort=relevance` to PubMed esearch too.
8. **Too many options cluttering responses** — collapsed "Answer mode" + "Evidence sources"
   controls into a hidden-by-default `<details>` in `index.html`/`style.css`.
9. **Wanted curriculum tags at top, not evidence-source list** — `renderEntryTagsHeader` now
   renders a `Root › Sub › Leaf` breadcrumb at the top of topic pages; source summary moved to
   the bottom as references.
10. **"Teaching session notes" panel replaced with page export** — removed all notes JS/HTML,
    added `setLastExportableResult` / `exportCurrentPageAsJson` + an "Export current page as
    JSON" button.
11. **Redundant lecture segments** — same lecture appeared multiple times (once per matched
    timestamp) in both the lecture-segments gallery and the videos list. Added
    `videoLectureKey()` + `bestVideoCardPerLecture()` in `app.js` to collapse to one
    best-scoring segment per distinct lecture before display caps apply. Covered by new
    `TestBestVideoCardPerLecture` in `tests/test_pathology_hub_chat_mvp.py`.

**Verification status:** full offline pytest suite green after every change (last known count
55/55); no `node` available in sandbox so JS edits were reviewed by hand instead of
`node --check`. **None of items 2–11 above have been confirmed live in a browser by the user
yet in this session** — the dev server was mid-restart (to pick up the new `.env`/secret-manager
key path) when the user ran out of context and asked to save progress. Item 1 (secrets) is the
one thing that must be re-verified first, since a broken key blocks testing everything else.

### Immediate next step
Restart `./scripts/run_local.sh` with `.env` re-sourced (see terminal), hit `/api/health` to
confirm `secrets.present: true` and no 401s, then click through a topic page live to confirm
items 2–11 actually look right in the browser (not just offline-test-green) — figures showing by
default, modal arrows on inline images, tag breadcrumb at top, one row per lecture, literature
citations that aren't just last-year's papers, export button working. Nothing has been
committed; commit only if/when the user asks.

## Current task (cloud / online agent)

**Cloud environment ready — next agent guides user through online steps.** Environment
`herndoch/pathology-hub-dev` is Active with snapshot; secrets verified working on a fresh
agent (`secrets.present: true`, Chat MVP `/api/health` 200 on port 8000). User wants to
run agents from phone/browser ([cursor.com/agents](https://cursor.com/agents)).

- **Handoff (read first):** `docs/HANDOFF_CLOUD_AGENT_ONLINE_NEXT_STEPS.md`
- **Branch:** `cursor/pathology-hub-chat-mvp`
- **Cloud hooks:** `.cursor/environment.json` (commits `3eb4aa8`, `5f69ee2`, `be7b1f8`)
- **Critical:** "Start Fresh" wipes secrets — re-add all 4 env vars, then **Save** (see handoff)
- **Default next work:** topic-page prebuild batch N=25–50, seed `20260711` (pilot passed 6/6)
- **Alternative:** backend local dev on `cursor/setup-dev-environment-0d85` (PR #12) if user chooses
- **Do NOT commit secrets**

## Prior task (completed — topic-page prepop pilot)

**Topic-page prepop pilot: PASS.** Built the combined deduped ABPath+PathOut Browse tag
index (8,054 leaves, 17 roots incl. a `Cytopathology` aggregate of all `Cyto_*` roots),
wired `static/app.js` Browse to load it live from `/static/browse_tag_index_v0_1.json`
(curated `BROWSE_TAXONOMY` kept only as an automatic fallback if that fetch ever fails),
drew the seeded pilot sample (N=6, seed `20260710`, ≥1 Cyto + ≥1 PathOut-only), and
prebuilt all 6 topic pages via the existing live `/api/chat` `topic_page` path (6/6 ok,
244 cards, 155 figures — figure-quality filters applied unchanged, no writes to the
quality-flags sidecar or curriculum SQLite). Added a small read-only
`GET /api/topic_prebuild?tag=…` lookup route; Browse leaf clicks try it first, else fall
back to the unchanged live query path. Offline suite still 42/42 green; live fallback
re-verified for a non-prebuilt leaf.

- Full plan: `docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md`
- Full results + next-batch recommendation: `docs/HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md`
  ("Handoff to following agent" section)
- Outputs (local, gitignored): `outputs/chat_mvp_topic_prepop_v0_1/`
  (`browse_tag_index_v0_1.json` + `.audit.json`, `pilot_sample_v0_1.json`,
  `pilot_prebuild_audit_v0_1.json`, `pages/*.json`+`.md` ×6)
- New scripts: `frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py`,
  `draw_pilot_sample_v0_1.py`, `prebuild_topic_pages_pilot_v0_1.py`
- **Known limitation carried forward:** a couple of tiny PathOut-only roots (`Eye`,
  `General_Pathology`, 1 leaf each) didn't fold into their closest ABPath sibling because
  the dedupe rule is literal-casefold-only (no fuzzy alias table) — cosmetic, not a data
  issue; flagged for a product decision before the next batch.
- **Not yet done:** a real browser click-through of Browse (tile → subcategory → leaf) —
  this pass verified the JS logic structurally (parse check + a Python-side replay of the
  exact lookup chain against the real generated index) and every backend endpoint via
  curl, but no actual DOM render was observed. Recommend that first before the next batch.

## Prior task (completed this session)

**Black cyto figure thumbs (Chat MVP):** Browse → Cytopathology → Common FNA /
Exfoliative Cytology showed solid-black Selected Images (caption "Cyto Thyroid
Bethesda"). Not 404s — HTTP 200 near-black stubs.

### Root cause

**(a) quality-flag miss** on staged extraction stubs, not deleted-URI masking:
- Live examples: `cyto_thyroid_bethesda_p0011/p0020/p0033_fig01_unidentified.jpeg`
  — GCS originals **and** public derivatives are identical **90×90 / 1150-byte**
  near-black JPEGs (`mean_l≈25`, `near_black≈0.37`).
- Dimension audit `TINY_DIM=120` would have flagged them, but these figure-only
  unidentified assets were outside the curriculum SQLite locator population, so
  they never entered `curriculum_figure_image_quality_flags_v0_1.jsonl`.
- At least **14** identical 1150-byte stubs under `cyto_thyroid_bethesda/`;
  Phase 1 `suppress_render` correctly still strips Tier-A aspect strips
  (e.g. cyto fig01 2592×235) on topic_page paths.

### Fix (Chat MVP only — sidecar/SQLite untouched)

- Client: after `<img>` decode, hide tiny (`<120px` edge) / near-black frames
  like broken links (`static/app.js` + `.img-defect-hidden`).
- Shared thresholds in `figure_quality_filter.py` (`is_tiny_decoded_image`,
  `is_near_black_sample`) + unit tests.
- `/api/search` now also applies Phase 1 suppress_render filter (was topic/chat
  only).

### Verify

```bash
frontend/pathology_hub_chat_mvp/scripts/run_local.sh
# Browse → Cytopathology → Common FNA / Exfoliative Cytology
# → Thyroid FNA (Bethesda system): black squares should disappear from gallery
frontend/pathology_hub_chat_mvp/.venv/bin/python -m unittest tests.test_pathology_hub_chat_mvp -v
```

### Remaining

Larger dark-but-contentful frames (e.g. p0262 460×306, mean_l≈45) are kept.
CORS may block canvas sampling on some proxy URLs; tiny-dim check still catches
the 90×90 family. Sidecar backfill of these stubs is optional later work (not
done — no pre-approval for quality-flag mutation).

ExpertPath clicking: no further help needed (parent dive already covered).

## Prior task (completed)

**Phase 3:** repaired `textbook_lean_figures.jsonl` for v0_2 deleted figure URIs and
uploaded to GCS. Branch: `cursor/pathology-hub-chat-mvp`.

### What was run (2026-07-10)

1. **`scripts/repair_textbook_lean_figures_after_delete_v0_3.py`** (new)
   - Input manifest: **3,055** deleted `gs://` URIs from
     `06_audits/.../delete_manifest_execute_20260708.txt`.
   - Downloaded canonical GCS
     `gs://pathology_hub/02_normalized/textbooks/lean/textbook_lean_figures.jsonl`.
   - Dropped rows whose `image_path`/`image_url` hit the delete manifest (web-map-style;
     backend `load_figures()` skips rows without a resolvable image anyway).
   - **68,218 → 65,163** lines; **3,055** dropped (exact 1:1 with delete manifest).
   - Top dropped sources: `gu_practical` 678, `hn_gnepp` 537, `gi_atlas` 451,
     `cyto_comprehensive_part_one` 447, `cyto_comprehensive_part_two` 421.
   - Post-repair verification: **0** remaining deleted-URI references.
   - Repair audit:
     `06_audits/curriculum_provenance_links/v0_1/textbook_lean_figures_repair_v0_3/repair_audit_repair20260710.json`
   - Git-tracked summary:
     `audits/textbook_lean_figures_repair_v0_3/repair_summary_v0_3.json`

2. **GCS upload** (`--upload`, upload audit written first per AGENTS.md)
   - `gs://pathology_hub/02_normalized/textbooks/lean/textbook_lean_figures.jsonl`
   - Upload audit:
     `06_audits/curriculum_provenance_links/v0_1/textbook_lean_figures_repair_v0_3/upload_audit_upload20260710.json`

### Boundaries preserved

- Quality-flags sidecar and curriculum SQLite untouched (read-only).
- Docstore / web figure map already repaired in v0_2; not re-touched.
- FAISS / SQLite FTS unchanged.
- Chat MVP Phase 1 `suppress_render` filter still handles Tier-A quality defects
  (separate from deleted-URI cleanup).

### Explicitly NOT done (blocked or deferred)

- Journals `source_url` liveness (Cloudflare bot-blocking — still inconclusive).
- Per-lecture diversification (blocked on backend `source_id`/`lecture_id` granularity).
- Full data-driven taxonomy expansion (approach b).
- Cloud Run cold restart to pick up repaired figures jsonl (pods cache until restart).

### Files touched

- `scripts/repair_textbook_lean_figures_after_delete_v0_3.py` (new)
- `outputs/textbook_lean_figures_repair_v0_3/` (local repaired artifact + input copy)
- `06_audits/curriculum_provenance_links/v0_1/textbook_lean_figures_repair_v0_3/`
- `audits/textbook_lean_figures_repair_v0_3/repair_summary_v0_3.json`
- `docs/ACTIVE_CONTEXT.md` (this file)

### Immediate next step

Cloud Run pods cache downloaded artifacts until cold restart — new instances pick up the
repaired GCS object automatically. Optional: force a revision restart / scale-to-zero if
live `/health` still reports `textbook_figure_records_loaded=67992` after a cold start
window. Expected post-restart load ≈ **65,163** minus any rows without resolvable images
(~226 historically → ~64,937).

Optional UI spot-check:

```bash
frontend/pathology_hub_chat_mvp/scripts/run_local.sh
# Browse → Head & Neck → Salivary → Mucoepidermoid carcinoma
```

Offline suite (unchanged by this data repair):

```bash
frontend/pathology_hub_chat_mvp/.venv/bin/python -m unittest tests.test_pathology_hub_chat_mvp -v
```

## Prior task (completed)

Executed the prioritized next-agent plan from
`docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md` (items 1–6). Branch:
`cursor/pathology-hub-chat-mvp`.

### What was verified live (items 1–2, prior turn)

- **Figure quality-flags join key:** live textbook `chunk_id` matches sidecar byte-for-byte
  (`tbchunk:...` scheme). Live cards have **empty `record_id`** — join on `chunk_id` only.
  Standalone `figures[]` have no `chunk_id`; join via `(source_id, fig_slot)` from
  `image_path`. Public derivatives can return HTTP 200 with degenerate dimensions (2592×235)
  — invisible to link-liveness probes.
- **Phase 2 link-liveness audit:** 99/100 URLs alive (1% dead — one WHO GYN 404). Audit:
  `06_audits/curriculum_provenance_links/v0_1/chat_mvp_figure_liveness_audit_20260710.json`.

### What shipped that session (items 1–6)

1. **Phase 1 figure-quality filter** — new `figure_quality_filter.py`. Read-only join against
   `outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`. Strips
   `figure_url`/`image_url` from Tier-A `suppress_render` cards (keeps text/page images);
   drops flagged figures from `figures[]`. Wired into all retrieval paths in `app.py`. Live:
   cyto query 10→8 figures (two `fig01` cyto_comprehensive_part_two strips suppressed).
2. **Item 3 — textbook figure source trace:** confirmed live API loads
   `textbook_lean_figures.jsonl` (67,992 records per `/health`); `image_path` matches GCS
   jsonl row; `figure_url` served via web figure map as `public_web_derivative`. Jsonl was
   **not** repaired in v0_2 but dead-link rate ~1% because public derivatives mask deleted
   originals. Audit:
   `06_audits/curriculum_provenance_links/v0_1/chat_mvp_textbook_figures_source_trace_20260710.json`.
   **Superseded by Phase 3 above** — jsonl now repaired and uploaded.
3. **Item 4 — WHO cross-mentions wired:** `_extract_who_cross_mentions()` in `app.py` returns
   `who_cross_mentions` on `/api/chat` topic_page responses. Client: **Cross-referenced
   Entities** panel in topic page (`renderWhoCrossMentions`, reuses `ddx-link-btn` nav).
4. **Item 5 — `min_per_source=8` stress test:** "invasive ductal carcinoma breast" — 218 raw →
   139 deduped → **120 capped** (cap engaged). Per-source after cap: who 13, textbooks 29,
   journals 28, pathout 22, videos 28 — all families with ≥8 deduped cards kept ≥8.
5. **Item 6 — taxonomy breadth (curated approach a):** +11 leaves in `BROWSE_TAXONOMY`
   (Traditional serrated adenoma; salivary: Epithelial-myoepithelial carcinoma, Myoepithelial
   carcinoma, Basal cell adenocarcinoma, Acinic cell carcinoma; bone/soft tissue: Chordoma,
   Meningioma). Also fixed `app.js` `TOPIC_PAGE_SOURCES` to drop `lectures` (matched server).
6. **Tests:** 40/40 pass (+4 `TestFigureQualityFilter`).

### User approval granted (2026-07-10) — Phase 3 executed this session

The user authorized Phase 3 figure jsonl repair + GCS upload without re-asking; that work
is now complete (see Current task above).

## Prior task (completed)

Investigation + limited prototype + planning session for the Chat MVP diversity/limits/WHO
cross-entity-extraction/figure-quality problems flagged during live Browse/`topic_page`
testing. Full detail, real measured numbers, and phased next-steps plan:
`docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md`. Summary:

- **Shipped:** live-verified the backend hard-caps `max_results` at 10 for every source (not
  an arbitrary client guess — kept `le=10` unchanged); raised `TOPIC_PAGE_MAX_CARDS` 72→120
  and `TOPIC_PAGE_MAX_FIGURES` 20→40 based on measured token-budget headroom (gpt-4.1-mini's
  1,047,576-token context window vs. the ~62k-107k tokens actually used); added an explicit
  `min_per_source` floor option to `cap_cards_diverse()`; fixed a real bug found while
  measuring (`lectures`/`videos` return byte-identical duplicate corpus content — dropped the
  redundant `lectures` call from `TOPIC_PAGE_SOURCES` and added dedup to the regular
  retrieval path too). Re-probed ovarian HGSC and salivary mucoepidermoid carcinoma
  before/after live.
- **Prototyped then wired (this session):** `who_section_mentions.py` — WHO cards carry
  explicit `entity_name`/`section` metadata; now surfaced as `who_cross_mentions` on topic
  pages with clickable taxonomy nav.
- **Shipped:** global client-side `<img>` `error` fallback; Phase 1 sidecar suppress_render
  filter (`figure_quality_filter.py`). Master plan at
  `docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md`.

## Prior task (completed)
reliability, citation tags, retrieval speed, and a light Google-style color theme. Full detail in
`frontend/pathology_hub_chat_mvp/README.md` ("Browse tab / Topic page mode", "Citation tags",
"Color theme" sections) — summary here:

1. **Source imbalance — fixed.** `topic_page` requests were reusing the sidebar's default 3
   sources (`textbooks`, `pathout`, `who`). Now server-enforced in `app.py` (`TOPIC_PAGE_SOURCES`,
   overridden regardless of sidebar state) to always request all 6 non-`curriculum` sources.
   Client (`app.js`) sends the same full set too, so the debug panel matches reality.
2. **Within-source diversity — fixed.** New `diversify_by_source_id()` in `pathology_backend.py`
   (round-robin re-rank by `source_id`, never drops data), applied to every result list in
   `app.py`'s `_run_retrieval`. Verified live: 3 distinct textbook `source_id`s correctly
   interleaved for the ovarian HGSC probe. Known limitation: lecture/video `source_id` is one
   constant across the whole corpus, so it currently has no effect there.
3. **Journal link reliability — investigated, documented, not "fixed" with a risky filter.** Live
   probe proves journal retrieval itself is genuinely live (`source_status.journals == "ok"`,
   real titles/DOIs) despite a stale `api_exposed_note` in `/api/health` claiming otherwise. About
   half of journal cards have no `source_url` at all; the ones that do point to
   Elsevier/`modernpathology.org`, which Cloudflare-bot-blocked every automated request we tried
   from this sandbox (also hit `pathologyoutlines.com`, a known-good domain, in the same window) —
   so link liveness could not be conclusively tested. Deliberately did not add a server-side
   HEAD-check filter (risk of false-positiving against the same bot-wall from Cloud Run and hiding
   valid citations). Kept journals in the default set since retrieval is proven; documented the
   caveat instead of hiding it.
4. **Citation tags — done.** `renderCitations` (shared by chat + topic-page citation lists) now
   shows a small muted chip from `primary_tag`/first `candidate_tags` entry, skipped for
   missing/`__UNMAPPED__` tags. Verified live: 36/47 cards in the ovarian HGSC probe carried a real
   tag.
5. **Speed — parallelized, model unchanged.** `staged_retrieve` now uses a `ThreadPoolExecutor`
   instead of a sequential for-loop (same single backend operation, just fanned out concurrently).
   Live: 6-source retrieval bounded by the slowest call (~17s) instead of a sequential sum
   (~22s) — and now requests MORE sources in LESS retrieval time than before. OpenAI synthesis
   (~35s of a ~52s total) is now the dominant cost for this mode; did not swap `OPENAI_MODEL`
   default since we couldn't validate a faster model's grounding compliance in this session —
   documented as a deferred, quality-gated optimization, not a silent limitation.
6. **Light theme — done.** `style.css` `:root` and every hardcoded color converted to a
   Google-Sans-inspired light palette (white/light-gray surfaces, `#1a73e8` accent, dark-gray
   text). Topic-page section bars intentionally kept dark (`#202124`) to match ExpertPath's own
   dark section bars on a light page; organ-system tile gradients kept as their own bold per-
   category colors (unrelated to the light/dark surface theme).

New offline tests (19 total, up from 12): `diversify_by_source_id` (no-op with 0/1 distinct
source_id, round-robin interleave without data loss, missing-key handling),
`staged_retrieve` concurrency (timing proves parallel, order preserved), `TOPIC_PAGE_SOURCES`
composition, and server-side source override for `topic_page` mode via `TestClient`.

## Prior task (completed — superseded details below)

The nested Browse tree itself (taxonomy, tile grid, chevron drill-down, dedicated topic-page
layout, DDx cross-linking, Ask/Browse tabs) was built in the session immediately before this one.
That session's own detailed notes are preserved below for the taxonomy/rendering implementation
specifics (data structures, matching thresholds, etc.) — treat this current-task section above as
the up-to-date status; the "Explicitly NOT done yet" list directly below is **stale** (all of those
items are now done) and kept only for implementation-detail context.

### What shipped that session (nested Browse tree)

Pick up the plan already scoped in the prior handoff: build `BROWSE_TAXONOMY` (static, curated,
real pathology sub-classification — ~15-17 top categories × subcategories × leaf entities) in
`app.js`, a tile-grid home view + chevron drill-down, a dedicated topic-page renderer (Key Facts
box, dark section bars, figure gallery reusing the existing modal-preview infra), fuzzy DDx→leaf
matching for cross-links, and breadcrumb navigation — all UI-only, still calling `/api/chat`
with `mode: "topic_page"` (already built and tested). Keep the existing flat organ-chip panel
working until the new tree fully replaces it in one clean edit, not a half-swap.

## Prior task (completed)

Pathology Hub Chat MVP — local GPT-style frontend over live `POST /evidence/search`.

### What was built

- Restored and committed `frontend/pathology_hub_chat_mvp/` (source had been lost; only
  `__pycache__` remained). FastAPI app + static chat UI.
- Backend client: `pathology_backend.py` — single operation `POST /evidence/search`,
  staged multi-source retrieval, citation card extraction, debug payloads.
- Optional OpenAI synthesis (`gpt_like`, `compare_sources`, `visual`, `html_teaching`) or
  `search_only` raw evidence.
- Secrets via `PATHOLOGY_HUB_API_KEY` / `HUB_API` and `OPENAI_API_KEY` (never logged).
- Tests: `tests/test_pathology_hub_chat_mvp.py` (offline parsing + mocked `/api/search`).
- **Experiment notes panel** (right sidebar): freeform textarea, auto-save to
  `localStorage` key `pathology_hub_experiment_notes`, Copy + Export markdown buttons.
- v2 TODO stub only: modal previews for `page_image_url`, `figure_url`, `video_time_url`.

### Run locally

```bash
frontend/pathology_hub_chat_mvp/scripts/run_local.sh
# open http://127.0.0.1:8000/
```

### Immediate next step

Set API keys in env and spot-check one pathology query with citations + debug panel.
Use experiment notes while testing; v2 items: citation image modals, provenance browser links.

## Prior task (completed)

Textbook index refresh after v0_2 figure-image GCS delete (docstore + web map).

### What was run (2026-07-09)

1. **`scripts/repair_textbook_figure_index_after_delete_v0_2.py`**
   - Input manifest: **3,055** deleted `gs://` URIs from
     `06_audits/.../delete_manifest_execute_20260708.txt`.
   - Downloaded canonical GCS inputs, repaired locally under
     `outputs/textbook_figure_index_repair_v0_2/`.
   - **Docstore** (`textbook_lean_vector_docstore.jsonl`): **79,320** lines in/out;
     **3,003** lines nulled `image_path` (matches pre-refresh staleness audit).
   - **Web figure map**: **49,525 → 47,772** lines; **1,753** orphaned rows
     dropped (matches pre-refresh staleness audit).
   - Post-repair verification: **0** remaining deleted-URI references in either
     artifact.
   - Repair audit:
     `06_audits/curriculum_provenance_links/v0_1/textbook_figure_index_repair_v0_2/repair_audit_repair20260709.json`
   - Git-tracked summary:
     `audits/textbook_figure_index_repair_v0_2/repair_summary_v0_2.json`

2. **GCS upload** (`--upload`, upload audit written first per AGENTS.md)
   - `gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl`
   - `gs://pathology_hub/02_normalized/textbooks/lean/textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl`
   - Upload audit:
     `06_audits/curriculum_provenance_links/v0_1/textbook_figure_index_repair_v0_2/upload_audit_upload20260709.json`

### Follow-ups

- `textbook_lean_figures.jsonl` — **done in Phase 3 (2026-07-10)**; see Current task.
- FAISS / SQLite FTS indexes unchanged (vector rows unchanged; only metadata
  stripped). Rebuild only if a downstream audit proves stale figure metadata
  affects retrieval ranking.
- Cloud Run pods cache downloaded artifacts until cold restart; new instances
  pick up repaired GCS objects automatically.
- **fig01-fallback** locator assignment remains a separate, not-yet-approved fix.

## Prior task (completed)

Post-delete sanity + downstream breakage audit (day after GCS delete and v0_2
locator strip).

### What was checked (2026-07-09)

1. **Local sanity** — v0_2 SQLite stripped; deleted GCS objects return **404**.
2. **Live evidence search** — **0** dead figure URLs in top-5 for 3 probe queries
   (audit:
   `06_audits/curriculum_provenance_links/v0_1/post_delete_evidence_figure_audit_20260709T223025Z.json`).
3. **Pre-refresh staleness** — docstore **3,003** lines + web map **1,753** lines
   still referenced deleted objects (now repaired above).

## Prior task (completed)

Deleted flagged textbook figure images from GCS and stripped their locators from
the derived provenance index (v0_2).

### What was run

1. **`scripts/build_curriculum_image_locator_strip_repairs_v0_2.py`**
   - Cleared `image_path` / `image_url` on **7,994** textbook rows (flagged
     `record_id` or matching flagged URL).
   - Wrote `outputs/curriculum_map_v0_4/curriculum_record_provenance_sidecar_repaired_v0_2.jsonl`
   - Rebuilt `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite`
   - Audit: `06_audits/curriculum_provenance_links/v0_1/curriculum_image_locator_strip_audit_v0_2.json`
   - Textbook partial locators: **37,099** (was ~29,117 on v0_1 index).

2. **`scripts/delete_flagged_textbook_figure_images_v0_2.py --execute`**
   - Deleted **3,055** unique objects under
     `gs://pathology_hub/01_staged/textbooks/assets/figure_images/` (from v0_1
     flagged CSV; 4,835 flagged rows).
   - Audit: `06_audits/curriculum_provenance_links/v0_1/figure_image_gcs_delete_v0_2/delete_audit_execute_execute_20260708.json`
   - Spot-check: sample deleted URLs return **404**.

3. **Browser defaults** now point at v0_2 SQLite; any quality-flagged row
   treats figure images as removed (no link, no preview).

### Boundaries preserved

- v0_1 sidecar/SQLite unchanged on disk (gitignored outputs).
- Normalized `curriculum_records_v0_4.jsonl` not mutated.
- Deletes limited to audit-flagged figure-image prefix only.

### Immediate next step

Restart provenance browser (uses v0_2 index by default) and spot-check a
formerly flagged row — should show no image URL and GCS 404 if probed:

```bash
tools/curriculum_provenance_browser/scripts/run_local.sh
```

## Prior task (completed)

Phase 2 — provenance browser bridge + UX polish (local only).

### What was built

- **Default search UX:** page load now searches all locator completeness (not
  partial-only). Blue info banner explains that quality suppress/warn examples
  require setting **Image quality flag** to Suppressed or Flagged.
- **Detail view links:** clickable `source_url`, computed `video_time_url`,
  `image_url` (hidden when Tier A suppressed), `who_html_gcs_path`, and PDF/video
  GCS URIs (via `storage.googleapis.com` hrefs).
- **Suggested evidence query panel:** detail view shows a derived
  `POST /evidence/search` JSON body (from `approved_tag` + `source_family`) with
  **Copy JSON** button; no API key in UI.
- `tools/curriculum_provenance_browser/evidence_bridge.py` — shared helpers for
  query derivation, GCS→HTTPS links, and `video_time_url` computation.
- `tools/curriculum_provenance_browser/scripts/probe_evidence_from_record.py`
  — `--record-id` CLI; reads SQLite read-only; optional live
  `/evidence/search` when `PATHOLOGY_HUB_API_KEY` or `HUB_API` is set; writes
  audit JSON under `06_audits/curriculum_provenance_links/v0_1/`; never prints
  secrets.
- Tests extended: **8/8 pass**
  (`tools/curriculum_provenance_browser/.venv/bin/python -m unittest
  tests.test_curriculum_provenance_browser -v`).

### Immediate next step

Run the browser locally and spot-check one detail row with links + evidence JSON:

```bash
tools/curriculum_provenance_browser/scripts/run_local.sh
# open http://127.0.0.1:8765/
# optional: probe live evidence for a record_id when API key is in env
tools/curriculum_provenance_browser/.venv/bin/python \
  tools/curriculum_provenance_browser/scripts/probe_evidence_from_record.py \
  --record-id "<record_id>"
```

## Prior task (completed)

Ran the requested read-only provenance browser and live evidence-search QA pass.
Short report saved at `docs/PROVENANCE_BROWSER_EVIDENCE_QA_20260708.md`.

### What was checked

- Confirmed the quality-flag/browser changes are already committed in
  `dad58eb Add textbook figure quality-flag sidecar and browser suppress/warn UI.`
- Started/used the local provenance browser at `http://127.0.0.1:8765/`.
- `/api/health` returned `ok=true`, SQLite present, quality-flags JSONL present,
  and `read_only=true`.
- API filters worked:
  - default `/api/search?limit=5`: `total=159771`
  - `quality=suppressed`: `total=3382`
  - `quality=flagged`: `total=4835`
  - `root=BST`: `total=18258`
  - `source_family=textbooks`: `total=98151`
  - `approved_tag=BST::Bone`: `total=8087`
- Detail API verified one suppressed row and one flagged row with expected
  `quality_flag` payloads.
- Opened the local UI in the Windows browser via `cmd.exe /C start`.
- Live evidence search authenticated without printing the key and returned
  source-specific result arrays for the three requested query bodies.

### Findings

- Provenance filters and quality-flag API joins work.
- UI confusion: default search is not quality-focused; users must set the
  `Image quality flag` dropdown to `Suppressed` or `Flagged` to reliably see
  the red/warn quality examples.
- Evidence response schema uses `textbook_results`, `pathout_results`,
  `who_results`, `lecture_results`, and `video_results`; it does not use a
  single top-level `results` list.
- Evidence query strength:
  - Strong: `tubular adenoma colon` with textbooks.
  - Strong: `LCIS breast` with textbooks/pathout/who.
  - Strong but duplicated: `branchial cleft cyst` with lectures returns both
    `lecture_results` and `video_results`.
- Evidence textbook page-image URLs did not hit the known Tier A suppressed
  figure-image families in this pass.

### Test status

- `tools/curriculum_provenance_browser/.venv/bin/python -m unittest tests.test_curriculum_provenance_browser -v`
  hung after `test_health ...`.
- Diagnostic run reached `after setup` and timed out on
  `TestClient.get('/api/health')`; live server `/api/health` and `/api/search`
  worked, so this appears isolated to in-process FastAPI/Starlette `TestClient`
  behavior in this environment.
- System `python3 -m unittest ...` cannot run the suite because system Python
  lacks `fastapi`.

### Recommendation

Keep the provenance debug UI separate from evidence search for now. Bridge
later with links from evidence result locator metadata into the provenance
browser, rather than merging the workflows now.

## Current task (completed)

Built the textbook figure image quality-flag sidecar and browser UI update
described in `docs/RUNBOOK_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md`, per
the runbook's final/approved (2026-07-08) tier table (used as-is, not
re-derived).

### Why (this task)

The full-population image dimension audit (52,540/52,540 textbook images,
see prior task below) actually completed after the stratified-8000 fallback
was already summarized. Full results:
`06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_full_v0_1.json`
— 9.16% overall flag rate. Re-analysis against the full population (not the
sample) found `gi_atlas` fig02/03/04 as the worst offenders (81.3%, 73.5%,
47.5% flag rates), in addition to the previously confirmed
`cyto_comprehensive_part_one/two` fig01 (2592x235 fixed crop) and `gu_practical`
fig01/02 (7x7 degenerate) patterns. Full evidence and tier rationale:
`docs/PROPOSAL_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md`.

### What was built

- `scripts/build_textbook_figure_image_quality_flags_v0_1.py` — new,
  sidecar-only, read-only script. Reads
  `flagged_figure_images_full_v0_1.csv` (4,835 flagged rows), tags each row
  `suppress_render` (Tier A `source_id`/`fig_slot` pairs from the runbook) or
  `warn_render` (every other flagged row), and writes:
  - `outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`
    (4,835 rows: `record_id`, `chunk_id`, `source_id`, `fig_slot`, `width`,
    `height`, `aspect_ratio`, `flags`, `tier`).
  - `06_audits/curriculum_provenance_links/v0_1/figure_image_quality_flags_audit_v0_1.json`
    (`schema_version`, `created_at`, `input_paths`, `output_paths`, `counts`
    with `total_rows`/`tier_a_count`/`tier_b_count`/per-`source_id` breakdown,
    `known_limitations`).
  - Counts: **3,382 Tier A (`suppress_render`)**, **1,453 Tier B
    (`warn_render`)**, 4,835 total. Matches the runbook's Tier A pair list
    exactly (11 `(source_id, fig_slot)` pairs).
- `tools/curriculum_provenance_browser/app.py` — loads the quality-flags
  JSONL read-only at startup (cached in-memory dict keyed by `record_id`, no
  SQLite schema change), attaches a `quality_flag: {tier, flags, width,
  height} | null` field to every `/api/search` row and to
  `/api/records/{id}`. Added an optional `quality` search filter
  (`all`/`suppressed`/`flagged`/`clean`) applied in-memory after the existing
  SQL query.
- `tools/curriculum_provenance_browser/static/index.html` — `suppress_render`
  rows show "Known extraction defect — image suppressed" plus flag reasons
  and parsed dimensions instead of the image locator line (other locator
  fields still render normally); `warn_render` rows get a visible "⚠ suspect
  dimensions" badge with reasons and width x height. Added a `quality`
  filter dropdown and a dedicated "Image quality" results column, plus a
  matching quality-flag block in the record detail view.
- `tests/test_curriculum_provenance_browser.py` — added a small fixture
  quality-flags JSONL (one Tier A, one Tier B row, keyed to two real
  `record_id`s sharing a rare `approved_tag` in the sqlite index) and two new
  tests: one asserting `/api/records/{id}` returns
  `quality_flag.tier == "suppress_render"` for the Tier A id and
  `"warn_render"` for the Tier B id (plus `null` for an unflagged record);
  one exercising the `quality` search filter's `all`/`suppressed`/`flagged`/
  `clean` values and its 422 on an invalid value. Full suite: **6/6 tests
  pass** (`tools/curriculum_provenance_browser/.venv/bin/python -m
  unittest tests.test_curriculum_provenance_browser -v`).

### Deviation from the runbook (documented, not a scope change)

The runbook says the `quality` filter is "applied in-memory after the
existing SQL query." Implemented literally with the SQL query's
`LIMIT`/`OFFSET` kept as-is, a `quality != "all"` filter would silently
under-fill or double-count pages (filtering a fixed-size page can shrink it
below `limit`, and the reported `total` would still be the pre-filter SQL
count). To keep `total` and pagination correct when a `quality` filter other
than `all` is requested, the SQL `WHERE` clause is unchanged, but
`LIMIT`/`OFFSET` are dropped from SQL and applied in Python after the
in-memory quality filter instead (the default `quality=all` path is
byte-for-byte the original SQL-paginated behavior, unchanged). No SQL filter
clause was added for `quality` itself, consistent with the runbook's
constraint.

### Immediate next step

Run the browser locally and visually confirm one Tier A and one Tier B
example:

```bash
tools/curriculum_provenance_browser/scripts/run_local.sh
# open http://127.0.0.1:8765/, filter "Image quality flag" = Suppressed/​Flagged
```

Do not start on the fig01-fallback logic change in
`scripts/build_curriculum_source_locator_repairs_v0_1.py` (separate,
not-yet-approved change) or re-run the network audit — both remain out of
scope per the runbook's stop condition.

## Prior task (completed)

Completed the textbook figure/page image dimension audit runbook using the
large fallback sample pass (`--sample-size 8000`) after the full 52,540-image
run proved too slow for the current session.

### Why

Manual spot-checks in the curriculum provenance browser found that textbook
figure image locators are frequently wrong or degenerate:

- 71.6% of textbook rows with an image point at the first figure slot
  (`fig01`) on the page; 95.2% of *page text chunks* with an image use this
  `fig01` fallback (from `scripts/build_curriculum_source_locator_repairs_v0_1.py`,
  which assigns the first figure seen on a page to any text chunk missing
  its own image).
- A 300-image random sample flagged ~10% as extreme aspect ratio, strip
  shaped, or near-zero pixel dimensions.
- 40/40 random `fig01` images from `cyto_comprehensive_part_one` /
  `cyto_comprehensive_part_two` were exactly `2592x235` pixels regardless of
  page or figure content — a fixed crop-region bug, not natural variation.
  `hn_gnepp` showed a similar fixed signature near `1313x118`.
- This matches a prior caveat already on record in
  `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/docs/00_MASTER_HANDOFF_FOR_CODEX.md`
  about reported header/footer crop junk.

### Tooling already built and validated (small scale only)

`scripts/audit_textbook_figure_image_dimensions_v0_1.py` — read-only,
sidecar-only. Parses JPEG/PNG/JP2 headers from a byte-range fetch (no PIL, no
full-image download) and flags extreme aspect ratio / strip shape / tiny
images. Validated on a 300-image random sample: 0 fetch errors, 0 unparsed
headers (added JP2/`.jpx` support after the first test run caught a gap).
Not yet run at full scale (52,540 unique textbook image locators).

### What was run

- Exact full command was started twice:
  `python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py --sample-size 0 --concurrency 24 --run-tag full`
- In the current environment the full run did not produce outputs within a
  reasonable interval, so the runbook fallback was used:
  `python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py --sample-size 8000 --concurrency 24 --run-tag stratified8000`
- A tiny diagnostic run also completed successfully:
  `python3 scripts/audit_textbook_figure_image_dimensions_v0_1.py --sample-size 10 --concurrency 4 --run-tag diag10`

### Immediate next step (for Codex or next agent)

Use the audit outputs below to decide whether a separate, explicitly-approved
repair pass should suppress known-bad `(source_id, fig_slot)` patterns or
prefer different textbook image assignment logic for `page_text_chunk` rows.
Do not write repairs in the same session unless the user explicitly reopens
that scope.

## Prior task

Local curriculum provenance browser for querying and debugging the repaired source locator SQLite index.

## Current state

- GCP user auth is active for `herndon.charlie@gmail.com`.
- ADC credentials were refreshed and saved under the local gcloud config.
- Active project is `pathology-annotation-project`.
- Secret Manager metadata has been verified for several external API credentials; values were not read.
- Prior memory indicates PathOut page-level records include `source_url` and figure URLs.
- Prior memory indicates accepted tags were root-grouped into a sidecar JSON.
- `scripts/audit_curriculum_provenance_links_v0_1.py` has been created and rerun with source-family-specific locator logic.
- The v0.1 audit processed 159,771 curriculum records.
- Source-family counts were: `abpath` 6,105; `textbooks` 98,151; `lectures` 53,378; `pathout` 1,752; `who` 385.
- ABPath is now classified as ontology/tag-origin metadata, not a source corpus requiring source links.
- A full record-level provenance sidecar now exists at `06_audits/curriculum_provenance_links/v0_1/record_provenance_sidecar_v0_1.jsonl`.
- Full lecture and textbook vector docstores were copied locally to `data/curriculum_provenance_repair_v0_1/` for repair joins.
- `scripts/build_curriculum_source_locator_repairs_v0_1.py` produced a repair sidecar and repaired provenance sidecar.
- Repair pass changed 71,420 records: 42,738 textbook rows and 28,682 lecture rows.
- Final locator completeness counts after repair: `abpath` 6,105 complete; `pathout` 1,752 complete; `who` 385 complete; `lectures` 49,537 complete and 3,841 partial; `textbooks` 69,034 complete and 29,117 partial.
- Remaining gaps after repair: lecture timestamp recovery for 3,841 rows, textbook page image or figure image recovery for 27,181 rows, and textbook raw PDF URI recovery for 2,338 rows.
- `scripts/build_curriculum_source_locator_index_v0_1.py` produced a derived rich SQLite provenance index with 159,771 `provenance_records` rows.
- `tools/curriculum_provenance_browser/` provides a local read-only FastAPI search/debug UI over the SQLite index.

## Immediate next step

Run the local browser and use it to evaluate query quality, partial provenance visibility, and source locator rendering before any downstream API or GPT integration.

```bash
tools/curriculum_provenance_browser/scripts/run_local.sh
# open http://127.0.0.1:8765/
```

## Intended output directory

`tools/curriculum_provenance_browser/`

## Expected local outputs

- `tools/curriculum_provenance_browser/app.py`
- `tools/curriculum_provenance_browser/static/index.html`
- `tools/curriculum_provenance_browser/scripts/run_local.sh`
- `tests/test_curriculum_provenance_browser.py`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_stratified8000_v0_1.json`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/flagged_figure_images_stratified8000_v0_1.csv`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_diag10_v0_1.json`
- `06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/flagged_figure_images_diag10_v0_1.csv`

## Boundaries

- Codex and Cursor may read from, write to, upload to, and mutate GCS when they decide that is needed for the assigned task.
- For planned upload paths, prefer an audit JSON with `schema_version`, input paths, output paths, counts, and known limitations.
- No overwrite of original normalized records.
- No modification of raw chunks, vector docstores, FAISS indexes, or prior curriculum map outputs.
- The browser is read-only and must not mutate the SQLite index from the UI.
- Sidecar-only repair maps are allowed after audit evidence supports them.

## Deferred ideas (not started, for later discussion)

- External literature/knowledge API integration is a **separate future
  workstream**, not yet started and not part of the current provenance/image
  audit work. Secret Manager already has credentials for `OncoKB`, `Elsevier`,
  `SpringerOpen`, `SpringerMeta`, and `NCBI` (see `docs/SECRET_REFERENCES.md`),
  but none of these are called anywhere in current backend/frontend code today.
- The existing `journals` source in `/evidence/search` is served from a local
  FAISS vector index built ahead of time, not a live pass-through to any of
  the five external APIs above.
- If this workstream is picked up later: keep it separate from Evidence RAG /
  curriculum provenance work per `AGENTS.md`'s "keep workstreams separate"
  rule, and note that `OncoKB` (genomic variant interpretation) is a
  different kind of API than the four literature/journal APIs.

## Coordination notes for agents

- Update this file when changing the current task, blocker, touched files, outputs, or next step.
- If another agent has changed files unexpectedly, stop and ask the user how to proceed.
- Keep generated large data under `outputs/`, `data/`, or `06_audits/` as appropriate; do not commit large generated corpora unless explicitly requested.
