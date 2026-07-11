# Plan: Chat MVP topic-page prepopulation (pilot) v0.1

Last updated: 2026-07-10  
Workstream: `frontend/pathology_hub_chat_mvp/` (keep separate per `AGENTS.md`)  
Branch: `cursor/pathology-hub-chat-mvp`  
Status: **plan only** — next agent executes the pilot, then stops and hands off

Related:

- Nav / product IA: [`docs/PLAN_CHAT_MVP_BROWSE_EXPERTPATH_INSPIRED_v0_1.md`](PLAN_CHAT_MVP_BROWSE_EXPERTPATH_INSPIRED_v0_1.md)
- Executable next-agent brief: [`docs/HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md`](HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md)
- Active pointer: [`docs/ACTIVE_CONTEXT.md`](ACTIVE_CONTEXT.md)
- Tag mock (combined mode): `frontend/pathology_hub_chat_mvp/static/tag_taxonomy_mock.html`
- Topic pipeline: `frontend/pathology_hub_chat_mvp/{app.py,pathology_backend.py,prompts.py,static/app.js}`

---

## 1. Goals

1. **Start** prepopulating topic pages from a **combined, deduped ABPath + PathOut** tag index (not books / `cyto_*` source folders).
2. Run a **small random pilot** first (recommended **N = 6**, seed **`20260710`**).
3. **Reflect the real index in the site** — Browse loads the generated index artifact (or a generated taxonomy derived from it), not only the hand-curated `BROWSE_TAXONOMY` starter list.
4. Prebuild = write **sidecars/cache once** under `outputs/`; never mutate normalized corpora, quality-flags sidecar, or curriculum SQLite.
5. Structure work so **this plan is what the next agent executes**, then **STOP** and fill a handoff for a following agent (batch scale-up).

## 2. Non-goals (this pilot)

- Full corpus prebuild (thousands of leaves).
- ExpertPath clone chrome (Topics/Images, Dx badge, Compare/CME, photo tiles).
- New backend operations (only `POST /evidence/search` via existing Chat MVP `/api/chat`).
- Fabricating URLs or entity-links not returned by evidence / taxonomy match.
- Mutating `curriculum_figure_image_quality_flags_v0_1.jsonl`, curriculum SQLite, or original normalized JSONL.
- GCS upload of prebuilt pages (local `outputs/` + audit JSON only unless a later handoff reopens upload).
- Regressing Phase 1/3 figure quality filters (`suppress_render`, client near-black/tiny hide).

---

## 3. Locked product decisions (must encode)

| # | Decision |
|---|----------|
| 1 | Browse nav = **combined, deduped ABPath + PathOut** topic tags — not books / `source_id` folders (`cyto_*`, etc.). |
| 2 | Books remain **retrieval sources only** behind `topic_page`. |
| 3 | **Cytopathology** = own top-level root aggregating all `Cyto_*` tag roots; **every root = top tile**. |
| 4 | Hub-native, not ExpertPath clone. |
| 5 | Single backend op: `POST /evidence/search` (Chat MVP wraps it); never fabricate URLs/entity-links. |
| 6 | `AGENTS.md`: audit JSON with `schema_version` / paths / counts / limitations; sidecars/manifests/audits only; quality-flags + curriculum SQLite **read-only**. |
| 7 | Prebuild generates topic_page content into sidecars/cache — **does not** overwrite normalized records. |

---

## 4. Index source of truth

### 4.1 Inputs (read-only)

| Corpus | Path | Role | Approx counts (local v0_2 snapshot) |
|--------|------|------|-------------------------------------|
| ABPath gold tags | `data/curriculum_map_v0_2/abpath_source_tags.jsonl` | Ontology leaves via `primary_tag` | **6,105** tags; **35** roots (incl. 21 `Cyto_*`) |
| PathOut AP-diagnostic pages | `data/curriculum_map_v0_2/pathout_tagged_pages_AP_DIAGNOSTIC_v1.jsonl` | Extra entity coverage via `primary_tag_governed` (fallback `primary_tag`) | **4,397** pages; ~**3,377** resolved tags after skip rules |

Do **not** use curriculum SQLite as the Browse nav source for this pilot (different workstream; stay read-only).

### 4.2 Skip / exclude rules (before dedupe)

Skip a PathOut row if its governed/primary tag:

- is missing/blank
- equals `_UNMAPPED_` / `__UNMAPPED__` (case-insensitive)
- starts with `UNRESOLVED_ROOT`

These are not browseable topic leaves.

### 4.3 Canonical tag string + provenance

**Canonical key for dedupe:** casefold of the full `Root::…::Leaf` path (`tag.lower()`).

**Canonical display string:**

1. If the tag exists in ABPath → use the **ABPath** `primary_tag` spelling (preferred casing).
2. Else → use PathOut’s governed/primary tag, but **normalize root casing** when the root casefolds to a known ABPath root (e.g. PathOut `HEME::…` → `Heme::…` when ABPath has `Heme`).
3. Provenance flag on each leaf:
   - `abpath` — ABPath only
   - `pathout` — PathOut only (after skips)
   - `both` — present in both under the same casefold key

**Observed overlap (local snapshot, for planning only — recompute in audit):**

- Exact-string both ≈ 1,426; casefold both ≈ 1,427
- PathOut-only (resolved) ≈ 1,950–1,951
- ABPath-only ≈ 4,679
- PathOut unresolved skipped ≈ 672

### 4.4 Tree shape for Browse

- Split `canonical_tag` on `::`.
- **Home roots:**
  - One synthetic root **`Cytopathology`** (`id: cyto`) whose children are all tags whose first segment starts with `Cyto_` (ABPath + PathOut, deduped).
  - Every other distinct first segment (non-`Cyto_*`) is its own top-level root/tile (`Breast`, `GI`, `Heme`, …).
- **Depth for UI (pilot):** keep Hub 3-level drill-down:
  - Level 0: root tile
  - Level 1: subcategory = second segment when present, else `"General"`
  - Level 2: leaf = last segment as **display label**; store full `canonical_tag` on the leaf for query/prebuild lookup
- Deeper ABPath paths (4+ segments) still collapse to: root → (segment[1] or General) → leaf label = last segment; full path remains the identity key.

Do **not** create nav folders from textbook `source_id`s (`cyto_thyroid_bethesda`, etc.).

### 4.5 Output artifact (index SoT for the site)

```text
outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.json
outputs/chat_mvp_topic_prepop_v0_1/browse_tag_index_v0_1.audit.json
```

Optional UI-shaped projection (same build step or tiny follow-on):

```text
frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json
```

(copy or symlink of the outputs index so the static app can `fetch` it without a Python build step at runtime)

#### Index schema (`browse_tag_index_v0_1.json`)

```json
{
  "schema_version": "browse_tag_index_v0_1",
  "generated_at": "ISO-8601 UTC",
  "inputs": {
    "abpath": "data/curriculum_map_v0_2/abpath_source_tags.jsonl",
    "pathout": "data/curriculum_map_v0_2/pathout_tagged_pages_AP_DIAGNOSTIC_v1.jsonl"
  },
  "counts": {
    "abpath_tags": 0,
    "pathout_pages_seen": 0,
    "pathout_tags_skipped": 0,
    "leaves_total": 0,
    "leaves_abpath_only": 0,
    "leaves_pathout_only": 0,
    "leaves_both": 0,
    "roots_total": 0,
    "cyto_leaves": 0
  },
  "dedupe_rules": {
    "key": "casefold(full_tag_path)",
    "canonical_preference": "abpath_spelling_then_pathout_with_abpath_root_casing",
    "provenance_values": ["abpath", "pathout", "both"],
    "skips": ["blank", "_UNMAPPED_", "UNRESOLVED_ROOT*"]
  },
  "roots": [
    {
      "id": "cyto",
      "label": "Cytopathology",
      "kind": "cyto_aggregate",
      "leaf_count": 0,
      "subcategories": [
        {
          "id": "cyto_gyn",
          "label": "Cyto_GYN",
          "leaf_count": 0,
          "leaves": [
            {
              "tag": "Cyto_GYN::Squamous::Atypical_Squamous_Cells_Undetermined_Significance_ASCUS",
              "label": "Atypical_Squamous_Cells_Undetermined_Significance_ASCUS",
              "provenance": "abpath",
              "query": "Atypical squamous cells of undetermined significance ASCUS cytology"
            }
          ]
        }
      ]
    }
  ],
  "known_limitations": [
    "Index is a local v0_2 snapshot; not proof of API exposure or vector coverage.",
    "UI collapses deep paths to 3 levels; full tag remains the leaf identity.",
    "PathOut-only leaves may retrieve thinly if evidence search lacks matching text."
  ]
}
```

`query` for each leaf: humanized last segment (underscores → spaces) plus light context from root/subcategory (e.g. append `cytology` for `Cyto_*`). This string is what `topic_page` retrieval uses — **not** a fabricated URL.

---

## 5. Pilot sample

### 5.1 Recommended parameters

| Param | Value |
|-------|--------|
| **N** | **6** (acceptable range 5–8) |
| **seed** | **`20260710`** |
| Stratification | Include **≥1** leaf with `tag` starting `Cyto_`; include **≥1** `provenance == "pathout"` if any PathOut-only leaves exist after skips; fill remainder uniformly at random from remaining leaves |

### 5.2 Selection algorithm (reproducible)

1. Build full leaf list from §4.
2. Partition into pools: `cyto`, `pathout_only`, `other`.
3. `random.Random(20260710)`:
   - draw 1 from `cyto` (if non-empty)
   - draw 1 from `pathout_only` (if non-empty; else note limitation and draw from `other`)
   - draw until N from `other` excluding already chosen tags
4. Write:

```text
outputs/chat_mvp_topic_prepop_v0_1/pilot_sample_v0_1.json
```

```json
{
  "schema_version": "topic_prepop_pilot_sample_v0_1",
  "n": 6,
  "seed": 20260710,
  "stratification": {
    "require_cyto": true,
    "require_pathout_only": true
  },
  "leaves": [
    {
      "tag": "...",
      "label": "...",
      "provenance": "both",
      "query": "...",
      "root_id": "cyto",
      "subcategory_id": "cyto_thyroid"
    }
  ]
}
```

---

## 6. Prebuild pipeline (per pilot leaf)

### 6.1 What to call

Reuse the **existing** Chat MVP topic_page path — do not invent a second retrieval stack.

Preferred options (pick one; document in audit):

**A (simplest for pilot):** HTTP against local uvicorn:

```bash
# Terminal A
cd frontend/pathology_hub_chat_mvp && ./scripts/run_local.sh

# Terminal B — for each pilot leaf
curl -sS -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "<leaf.query>",
    "mode": "topic_page",
    "category_context": "<Root label> > <Subcategory label>",
    "include_figures": true,
    "max_figures": 8
  }'
```

**B (script wrapping app helpers):** new script under workstream only, e.g.

```text
frontend/pathology_hub_chat_mvp/scripts/prebuild_topic_pages_pilot_v0_1.py
```

that imports `ChatRequest` / `_run_topic_page_retrieval` / `_answer_topic_page` from `app.py` (or calls the same FastAPI route via `TestClient`). Keep it in the Chat MVP workstream.

Server already forces `TOPIC_PAGE_SOURCES` for `topic_page` and applies figure quality filters — **do not bypass** `_apply_figure_quality_filters` / Phase 1 `suppress_render`.

### 6.2 Secrets / Cloud Run (required for live synthesis)

| Need | How |
|------|-----|
| Evidence search | `PATHOLOGY_HUB_API_KEY` or `HUB_API`, or gcloud Secret Manager `PATHOLOGY_HUB_API_KEY` in project `pathology-annotation-project` |
| Backend URL | default `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app` (`PATHOLOGY_HUB_API_URL` override) |
| OpenAI synthesis | `OPENAI_API_KEY` or Secret Manager `OPENAI` — **required** for real topic_page answers |
| Health check | `GET http://127.0.0.1:8000/api/health` before batch — confirm secrets present (no values logged) |

Without OpenAI, do **not** claim pages are prebuilt; at most write a `search_only`-style sidecar and mark `synthesis_status: skipped` in limitations.

Expect ~45–60s+ per leaf (multi-query retrieval + long synthesis). Budget ~6–10 minutes for N=6 plus retries.

### 6.3 Sidecar outputs (per leaf)

Directory:

```text
outputs/chat_mvp_topic_prepop_v0_1/pages/
```

Filename: slug from canonical tag (replace `::` with `__`, safe chars only), e.g.

```text
outputs/chat_mvp_topic_prepop_v0_1/pages/Cyto_GYN__Squamous__Atypical_Squamous_Cells_Undetermined_Significance_ASCUS.json
outputs/chat_mvp_topic_prepop_v0_1/pages/Cyto_GYN__Squamous__Atypical_Squamous_Cells_Undetermined_Significance_ASCUS.md
```

#### Page sidecar schema (JSON)

```json
{
  "schema_version": "topic_page_prebuild_v0_1",
  "tag": "Cyto_GYN::Squamous::Atypical_Squamous_Cells_Undetermined_Significance_ASCUS",
  "label": "Atypical_Squamous_Cells_Undetermined_Significance_ASCUS",
  "provenance": "abpath",
  "query": "...",
  "category_context": "Cytopathology > Cyto_GYN",
  "generated_at": "ISO-8601 UTC",
  "ok": true,
  "model": "gpt-4.1-mini",
  "answer_markdown": "...",
  "cards": [],
  "figures": [],
  "who_cross_mentions": [],
  "retrieval_debug_summary": {
    "cards_capped": 0,
    "query_variants": [],
    "source_status": {}
  },
  "known_limitations": [
    "Prebuilt snapshot; live /api/chat may differ after corpus/backend changes.",
    "Figure list already passed Chat MVP suppress_render / quality filters at build time."
  ]
}
```

Markdown sidecar: title + `answer_markdown` only (human review). Cards/figures stay in JSON.

**Do not** write into `data/curriculum_map_v0_2/` or any `02_normalized` path.

### 6.4 Pilot audit JSON (AGENTS.md)

```text
outputs/chat_mvp_topic_prepop_v0_1/pilot_prebuild_audit_v0_1.json
```

Must include:

- `schema_version`: `topic_prepop_pilot_audit_v0_1`
- `input_paths` (index + sample + API base URL host only)
- `output_paths` (pages dir, md/json lists)
- `counts` (`n_requested`, `n_ok`, `n_failed`, figures/cards totals)
- `seed`, `pilot_tags`
- `known_limitations`
- `figure_quality_note`: Phase 1 filters applied; quality-flags sidecar and SQLite untouched

---

## 7. Site reflection (index in Browse UI)

### 7.1 Required behavior for pilot

1. **Load** `browse_tag_index_v0_1.json` (static copy under `frontend/pathology_hub_chat_mvp/static/` preferred).
2. **Replace** runtime use of hand-curated-only `BROWSE_TAXONOMY` as the Browse tree source — either:
   - **Preferred:** `fetch('/static/browse_tag_index_v0_1.json')` (or `/browse_tag_index_v0_1.json` if mounted) and build tiles/lists from `roots[]`, **or**
   - Generate a JS module / JSON once and keep a thin fallback stub if fetch fails (show error hint, do not silently revert to claiming the old list is the index).
3. Home tiles = every root in the index (Cytopathology aggregate + all non-cyto roots). Tile count text should say **topic tags** / leaf counts from the index — not “starter topics” from the old curated list once the index is live.
4. Leaf click:
   - If a prebuilt sidecar exists for that `tag` → serve/render it (new tiny `GET /api/topic_prebuild?tag=…` **or** static fetch of the page JSON under a mounted outputs path). Prefer a small FastAPI route that reads only from `outputs/chat_mvp_topic_prepop_v0_1/pages/` by tag slug.
   - Else → existing live `POST /api/chat` `mode: "topic_page"` fallback (unchanged).
5. DDx cross-links: rebuild leaf index from the loaded tag index labels/tags; still never fabricate links.

### 7.2 Files expected to touch (pilot implementation)

| Touch | Do not touch |
|-------|----------------|
| New: index builder script under `frontend/pathology_hub_chat_mvp/scripts/` | `data/curriculum_map_v0_2/*` (read-only) |
| `outputs/chat_mvp_topic_prepop_v0_1/**` | quality-flags sidecar |
| `frontend/pathology_hub_chat_mvp/static/app.js` (load index + prebuild serve path) | curriculum SQLite |
| Optional: `app.py` route to read prebuild JSON | GCS normalized corpora |
| `frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json` | ExpertPath clone features |
| Tests under `tests/test_pathology_hub_chat_mvp.py` if needed | Other workstreams |

Keep glyph/gradient map for known roots; unknown roots can use a neutral default gradient.

### 7.3 Pilot UX honesty

- Prebuilt pages: optional small “Prebuilt (pilot)” note in Browse leaf view — do not claim full corpus coverage.
- Index reflection means Browse shows **real combined tag roots/leaves** (at least the tree from the index file). For pilot, it is OK if only N leaves have prebuilt sidecars while the rest fall back to live synthesis.

---

## 8. Success criteria (pilot)

1. `browse_tag_index_v0_1.json` exists with `schema_version`, counts, roots including **Cytopathology** aggregate, and provenance on leaves.
2. Matching `.audit.json` for the index build.
3. `pilot_sample_v0_1.json` with seed `20260710`, N=6 (or documented 5–8), ≥1 Cyto, ≥1 PathOut-only when available.
4. N page sidecars (JSON + MD) under `pages/` with `schema_version: topic_page_prebuild_v0_1`.
5. `pilot_prebuild_audit_v0_1.json` complete per §6.4.
6. Local Browse loads the **index** (not curated-only taxonomy as SoT); spot-check: Cyto root shows `Cyto_*` branches; no `cyto_*` book folders.
7. Clicking a prebuilt pilot leaf renders Key Facts / sections / figures without live wait (or clearly from cache); a non-prebuilt leaf still live-falls-back.
8. Offline unit tests still pass; figure quality filters still applied on live path; no writes to quality-flags or SQLite.
9. Executing agent fills **Handoff to following agent** in the handoff doc and **STOPS**.

---

## 9. Explicit STOP after pilot

After §8 is met (or blocked with written limitations):

1. **Do not** start the next batch (no N=50/100 scale-up in the same session unless the user reopens).
2. Fill the template in [`docs/HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md`](HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md) → section **Handoff to following agent**.
3. Update [`docs/ACTIVE_CONTEXT.md`](ACTIVE_CONTEXT.md) current-task to “pilot complete — awaiting following agent”.
4. Stop.

### What the following agent should receive

- Status (pass / partial / blocked)
- Artifact paths + counts
- Sample tags + local Browse URLs / reproduction steps
- Blockers (secrets, cold API, empty PathOut-only pool, etc.)
- Recommended next batch size (suggest **25–50** if pilot clean; **10** if flaky)

---

## 10. Suggested implementation order (for executing agent)

1. Read this plan + handoff + Browse plan + `ACTIVE_CONTEXT.md`.
2. Confirm secrets via `/api/health`.
3. Implement index builder → write index + audit.
4. Copy/serve index into static; wire Browse to load it.
5. Draw pilot sample (seed `20260710`).
6. Prebuild N pages → sidecars + pilot audit.
7. Wire leaf → prebuild if present else live.
8. Smoke UI + unit tests.
9. Fill following-agent handoff → STOP.

---

## 11. Known limitations (plan-level)

- Local tag JSONL is a snapshot; counts must be recomputed in audits — do not treat planning numbers as proof.
- Full index in the UI may be large (~6–8k leaves); pilot may need virtualized lists or “load subcategory on demand” — acceptable if home + one root drill-down works.
- Journals / lecture diversification limitations from README still apply to live and prebuilt evidence alike.
- Prebuilt answers go stale when corpora or prompts change — sidecars are cache, not source of truth.
