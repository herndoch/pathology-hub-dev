# Handoff: Topic-page prepop pilot — next agent

Date: 2026-07-10  
Workstream: `frontend/pathology_hub_chat_mvp/`  
Branch: `cursor/pathology-hub-chat-mvp`  
Mode: **execute the pilot, then STOP and fill the following-agent section**

Full plan (source of truth for decisions/schemas):  
[`docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md`](PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md)

Nav product decisions:  
[`docs/PLAN_CHAT_MVP_BROWSE_EXPERTPATH_INSPIRED_v0_1.md`](PLAN_CHAT_MVP_BROWSE_EXPERTPATH_INSPIRED_v0_1.md)

---

## Read first (in order)

1. `docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md` — goals, schemas, STOP rules
2. `docs/PLAN_CHAT_MVP_BROWSE_EXPERTPATH_INSPIRED_v0_1.md` — locked Browse nav (combined ABPath+PathOut; cyto root; books ≠ nav)
3. `docs/ACTIVE_CONTEXT.md` — current pointer + figure-quality constraints
4. `frontend/pathology_hub_chat_mvp/README.md` — run/secrets/`topic_page` behavior
5. Skim: `static/app.js` (`BROWSE_TAXONOMY`, `loadLeafTopicPage`), `app.py` (`topic_page` path, figure filters), `static/tag_taxonomy_mock.html` (combined-mode mock)

---

## Exact steps

### 1. Preconditions

```bash
cd /home/herndonch/pathology-hub-dev
git status   # expect work on cursor/pathology-hub-chat-mvp; do not switch workstreams
cd frontend/pathology_hub_chat_mvp
./scripts/run_local.sh
# other terminal:
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool
```

Confirm `PATHOLOGY_HUB_API_KEY`/`HUB_API` and `OPENAI_API_KEY` (or Secret Manager) are present. Without both, stop and record blocker — do not fake synthesis.

### 2. Build combined deduped tag index

Create script (suggested path):

`frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py`

Inputs (read-only):

- `data/curriculum_map_v0_2/abpath_source_tags.jsonl`
- `data/curriculum_map_v0_2/pathout_tagged_pages_AP_DIAGNOSTIC_v1.jsonl`

Rules (must match plan §4):

- Dedupe key = `tag.lower()`
- Canonical spelling prefer ABPath; PathOut-only keep PathOut path with ABPath root casing when root casefolds match (e.g. `HEME` → `Heme`)
- Provenance: `abpath` | `pathout` | `both`
- Skip blank / `_UNMAPPED_` / `UNRESOLVED_ROOT*`
- Aggregate all `Cyto_*` under root `Cytopathology` (`id: cyto`); every other root = top tile

Outputs:

```text
outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json
outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json
frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json   # copy for UI fetch
```

Example command:

```bash
frontend/pathology_hub_chat_mvp/.venv/bin/python \
  frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py
```

### 3. Draw pilot sample

N=**6**, seed=**20260710**, ≥1 `Cyto_*`, ≥1 PathOut-only if available.

```text
outputs/chat_mvp_topic_prepop_v0_1/pilot_sample_v0_1.json
```

(Can be a flag on the same script or a second tiny script.)

### 4. Reflect index in Browse UI

- Change `static/app.js` so Browse loads `browse_tag_index_v0_1.json` as the tree SoT (replace curated-only `BROWSE_TAXONOMY` as the live nav source).
- Keep Hub tiles (glyph/gradient); Cytopathology remains its own top tile.
- Do **not** add `cyto_*` book folders.
- Rebuild DDx leaf index from loaded tags/labels.
- Leave Ask tab / live `topic_page` intact.

### 5. Prebuild pilot pages

For each leaf in `pilot_sample_v0_1.json`, call existing `POST /api/chat` with `mode: "topic_page"` (curl loop or `scripts/prebuild_topic_pages_pilot_v0_1.py`). Must go through figure quality filters (do not bypass).

Write:

```text
outputs/chat_mvp_topic_prepop_v0_1/pages/<tag_slug>.json
outputs/chat_mvp_topic_prepop_v0_1/pages/<tag_slug>.md
outputs/chat_mvp_topic_prepop_v0_1/pilot_prebuild_audit_v0_1.json
```

Schemas: plan §6.3–6.4 (`schema_version`, tag, query, cards, figures, answer_markdown, generated_at, known_limitations).

### 6. Serve prebuilt when present

- Add a small read-only route (e.g. `GET /api/topic_prebuild?tag=…`) that loads only from `outputs/chat_mvp_topic_prepop_v0_1/pages/`, **or** static-serve that directory.
- `loadLeafTopicPage`: try prebuild → else existing live `/api/chat` fallback.
- Never fabricate URLs/entity-links.

### 7. Verify

```bash
# UI: Browse home shows index roots; open Cytopathology; open one prebuilt leaf; open one non-prebuilt leaf (live fallback)
frontend/pathology_hub_chat_mvp/.venv/bin/python -m unittest tests.test_pathology_hub_chat_mvp -v
```

Confirm: no writes to quality-flags sidecar or curriculum SQLite; Phase 1 suppress_render / client near-black hide still active on live path.

### 8. STOP

Fill **Handoff to following agent** below. Update `docs/ACTIVE_CONTEXT.md` current-task to pilot-complete. **Do not** start the next batch.

---

## Commands cheat sheet

```bash
# Index build (after script exists)
frontend/pathology_hub_chat_mvp/.venv/bin/python \
  frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py

# Local app
cd frontend/pathology_hub_chat_mvp && ./scripts/run_local.sh

# Health
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool

# One live topic_page probe (fallback path)
curl -sS -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"ASCUS cytology","mode":"topic_page","category_context":"Cytopathology > Cyto_GYN","include_figures":true,"max_figures":8}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("ok"), d.get("answer_error"), len(d.get("figures") or []), len((d.get("answer") or "")[:80]))'

# Unit tests (repo root)
frontend/pathology_hub_chat_mvp/.venv/bin/python -m unittest tests.test_pathology_hub_chat_mvp -v
```

---

## Files to touch / not touch

### Touch (expected)

- `frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py` (new)
- `frontend/pathology_hub_chat_mvp/scripts/prebuild_topic_pages_pilot_v0_1.py` (new, optional if using curl)
- `outputs/chat_mvp_topic_prepop_v0_1/**` (index, sample, pages, audits)
- `frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json`
- `frontend/pathology_hub_chat_mvp/static/app.js`
- `frontend/pathology_hub_chat_mvp/app.py` (optional prebuild GET)
- `tests/test_pathology_hub_chat_mvp.py` (only if needed)
- `docs/ACTIVE_CONTEXT.md` (status after done)
- This file — **Handoff to following agent** section

### Do not touch

- `data/curriculum_map_v0_2/*` (read-only inputs)
- Curriculum SQLite under `outputs/` or GCS
- Figure quality-flags sidecar / any `suppress_render` source data (read-only)
- Normalized corpora / GCS uploads (unless user reopens)
- Other workstreams (provenance browser, GPT Builder, backend deploy)
- Full-corpus prebuild / ExpertPath clone features

---

## Definition of done (pilot)

- [ ] Combined index + audit written with real counts and Cyto aggregate root
- [ ] Static/UI loads that index for Browse (not curated-only SoT)
- [ ] Pilot sample N=6 seed=20260710 with stratification noted
- [ ] N prebuilt page JSON(+MD) sidecars + pilot audit
- [ ] Prebuilt leaf serves cache; other leaves live-fallback
- [ ] Unit tests green; figure-quality behavior not regressed
- [ ] Following-agent handoff section filled
- [ ] STOP — no scale-up batch

---

## Handoff to following agent

### Status

- [x] Pass
- [ ] Partial
- [ ] Blocked

Summary (2–4 sentences):

```text
Pilot executed end-to-end and passed all definition-of-done items. Built the combined
deduped ABPath+PathOut tag index (8,054 leaves, 17 roots incl. Cytopathology aggregate),
wired Browse (app.js) to load it as the live tree source with a curated-taxonomy fallback
if the fetch ever fails, drew the seeded N=6 sample (>=1 Cyto, >=1 PathOut-only), and
prebuilt all 6 topic pages via the existing live /api/chat topic_page path (6/6 ok, 244
cards, 155 figures, figure-quality filters applied unchanged). Added a small read-only
GET /api/topic_prebuild lookup route and wired the client to try it before falling back
to a live query. Unit suite still 42/42 green; live fallback path re-verified working for
a non-prebuilt leaf (ASCUS cytology probe). No writes to quality-flags sidecar or
curriculum SQLite at any point.
```

### Artifacts

| Artifact | Path | Notes |
|----------|------|-------|
| Tag index | `outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json` | 8,054 leaves / 17 roots |
| Index audit | `outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json` | mirrors index `counts` |
| Pilot sample | `outputs/chat_mvp_topic_prepop_v0_1/pilot_sample_v0_1.json` | seed `20260710`, N=6 |
| Pages dir | `outputs/chat_mvp_topic_prepop_v0_1/pages/` | 6/6 ok (JSON+MD each) |
| Pilot audit | `outputs/chat_mvp_topic_prepop_v0_1/pilot_prebuild_audit_v0_1.json` | 6/6 ok, 244 cards, 155 figures |
| UI index copy | `frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json` | served via existing `/static` mount |

Counts (from `browse_tag_index_v0_1.json`'s `counts`, real, not planning estimates):

```text
abpath_tags: 6105
pathout_pages_seen: 4397
pathout_tags_skipped: 673
pathout_tags_resolved: 3724
leaves_total: 8054
leaves_abpath_only: 4678
leaves_pathout_only: 1936
leaves_both: 1440
roots_total: 17
cyto_leaves: 1551
pilot_ok: 6 / 6
```

### Sample tags / URLs

All 6 confirmed served correctly via `GET /api/topic_prebuild?tag=<tag>` (found=true,
ok=true, non-empty `answer_markdown`) and via curl-loop verification against the running
local app.

| Tag | Provenance | Prebuilt? | How to open |
|-----|------------|-----------|-------------|
| `Cyto_Thoracic::Malignant::Carcinoma::Carcinosarcoma` | abpath | yes (41→ dedup 41 cards, 24 figures) | Browse → Cytopathology → Cyto_Thoracic → Carcinosarcoma |
| `Heme::Other::Normal_Histology::Age_Related_Changes` | pathout (PathOut-only) | yes (48 cards, 34 figures) | Browse → Heme → Other → Age_Related_Changes |
| `GU::Prostate::Hematolymphoid::Lymphoma_Leukemia` | abpath | yes (54 cards, 33 figures) | Browse → GU → Prostate → Lymphoma_Leukemia |
| `Thorax_Mediastinum::Lung::Inflammatory::Immune::Hypersensitivity_Pneumonitis` | both | yes (35 cards, 32 figures) | Browse → Thorax_Mediastinum → Lung → Hypersensitivity_Pneumonitis |
| `Neuro::Cyst::Dermoid_Cyst` | abpath | yes (31 cards, 20 figures) | Browse → Neuro → Cyst → Dermoid_Cyst |
| `Peds::BST::Soft_Tissue::Juvenile_Hyaline_Fibromatosis` | abpath | yes (35 cards, 12 figures) | Browse → Peds → BST → Juvenile_Hyaline_Fibromatosis |

Any other leaf in the index (8,048 of 8,054) is **not** prebuilt and falls back to the
existing live `/api/chat` `topic_page` path unchanged — re-verified live for
"ASCUS cytology" (`Cytopathology > Cyto_GYN` context): `ok=true`, 20 figures, non-empty
answer.

Local reproduction:

```bash
cd frontend/pathology_hub_chat_mvp && ./scripts/run_local.sh
# open http://127.0.0.1:8000/ → Browse tab (loads /static/browse_tag_index_v0_1.json on
# startup; home tile text says "N topic tags across N roots" when the index loaded, or a
# visible "index unavailable" hint if it fell back to curated taxonomy)
```

### Blockers / limitations

```text
- Root-casing dedupe is literal casefold-only per the plan (no fuzzy alias table): a few
  small PathOut-only roots did NOT merge into their closest ABPath sibling because the
  root strings don't casefold-match, e.g. PathOut "Eye" (1 leaf) and "General_Pathology"
  (1 leaf) stayed as their own tiny top-level tiles instead of folding into ABPath
  "Eye_Orbit". This is the plan's rule working as specified, not a bug, but worth a
  follow-up decision (fuzzy root alias table?) before the next batch if it matters
  visually. Both roots have exactly 1 leaf each (their tags contain "PathOut_Residual_
  Generated" as the leaf name) — cosmetic, not a data-loss issue.
- Deep-path collapsing to 3 UI levels is lossy by design (per plan): the full tag stays
  the identity key end-to-end (index leaf, sample, prebuild filename, /api/topic_prebuild
  lookup), so no functional loss — only the visual subcategory grouping is shallow for
  leaves 4+ segments deep.
- Client-side JS syntax could not be checked with a real browser engine in this sandbox
  (no Node.js install permission, no browser-automation tab available). Verified instead
  via: (1) full-file parse with esprima after normalizing pre-existing `?.`/`??` operators
  (which esprima's ES5/6 parser doesn't support) — passed; (2) a Python-side structural
  replay of the exact root_id/subcategory_id/tag lookup chain app.js performs, using the
  real generated index JSON for all 6 pilot leaves — all resolved correctly; (3) all
  backend endpoints app.js calls (`/api/health`, `/static/browse_tag_index_v0_1.json`,
  `/api/topic_prebuild`, `/api/chat`) were curl-verified directly. A real browser
  click-through of Browse → tile → subcategory → leaf was NOT done — recommend that as
  the first thing the following agent (or a human) does before trusting the UI fully.
- Prebuilt sidecars are a point-in-time cache (per plan) — will go stale if corpus/backend
  changes; `known_limitations` in each page JSON documents this.
- Journal/lecture diversification limitations already on record in README/ACTIVE_CONTEXT
  apply identically to live and prebuilt evidence.
```

### Recommended next batch

- Suggested N: **25–50** — pilot was clean (6/6 ok, 0 failures, secrets present, live
  fallback re-verified)
- Suggested next seed: integer `20260711` (or `20260710_batch2` if preferred)
- Priority: more `Cyto_*` + high-traffic organ roots (Breast, GI, GU, Skin, HN, GYN);
  defer huge PathOut-only "Concept"/residual dumps if a quick retrieval spot-check shows
  thin coverage
- Consider (optional, needs a product decision first): a small fuzzy root-alias table so
  PathOut "Eye" folds into ABPath "Eye_Orbit" etc. — currently intentionally NOT done
  (literal casefold-only dedupe per this plan)
- Recommend a real browser click-through smoke test (tile → subcategory → leaf, both a
  prebuilt and non-prebuilt leaf) before the next batch, since this pass could only verify
  the underlying data/API contracts, not actual DOM rendering
- Still out of scope until reopened: GCS upload of pages; SQLite/quality-flag mutation;
  full corpus; ExpertPath clone chrome

### Files changed (pilot PR candidates)

```text
New:
  frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py
  frontend/pathology_hub_chat_mvp/scripts/draw_pilot_sample_v0_1.py
  frontend/pathology_hub_chat_mvp/scripts/prebuild_topic_pages_pilot_v0_1.py
  frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json  (generated, copied)

Modified:
  frontend/pathology_hub_chat_mvp/app.py           (+json import, +TOPIC_PREBUILD_PAGES_DIR,
                                                     +GET /api/topic_prebuild route)
  frontend/pathology_hub_chat_mvp/static/app.js    (browseIndex load/fallback, unified
                                                     root/subcategory/leaf model, prebuild-
                                                     first loadLeafTopicPage, DDx/WHO nav
                                                     payloads carry tag/query now)
  frontend/pathology_hub_chat_mvp/static/style.css (+.chevron-count, +.topic-prebuilt-hint)
  docs/ACTIVE_CONTEXT.md                            (status → pilot complete)

Local-only (gitignored outputs/, not part of any PR):
  outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json
  outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json
  outputs/chat_mvp_topic_prepop_v0_1/pilot_sample_v0_1.json
  outputs/chat_mvp_topic_prepop_v0_1/pilot_prebuild_audit_v0_1.json
  outputs/chat_mvp_topic_prepop_v0_1/pages/*.json, *.md  (6 leaves)

Note: app.py/figure_quality_filter.py/tests/app.js/style.css already had unrelated
in-flight changes from the prior session's "black cyto figure thumbs" fix before this
pilot started (see ACTIVE_CONTEXT.md "Prior task" section above this one) — those are
not part of this pilot's diff but are in the same uncommitted working tree.
```
