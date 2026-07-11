# Handoff: Chat MVP UX bugs (user-reported 2026-07-11)

Branch: `cursor/pathology-hub-chat-mvp`  
Last pushed: `02a9fbb`  
User screenshots saved under Cursor assets (compare modal, compare table, HN browse subcats, pleomorphic citations).

---

## TL;DR for next agent

The user tested **Compare**, **Browse HN subcategories**, **Pleomorphic Adenoma topic page**, and **citation labels**. Several Phase 1 fixes only partially landed. Do **not** claim PathOut/textbook label cleanup is done until **inline answer links**, **prebuild cache**, and **all UI surfaces** are fixed.

---

## 1. Compare: unrelated entities mixed (Burkitt ↔ pancreas serous cystadenoma)

**User question:** “How is pancreas cystadenoma associated with Burkitt?”

**Answer:** They are **not** clinically associated. This is a **Compare UX/retrieval bug**.

**What user saw:**
- Compare view: “Compare Diagnoses (4)” with Burkitt Lymphoma column + other columns.
- Lightbox opened on an image captioned **Serous cystadenoma** with a PathOutlines pancreas cyto JPEG — while Burkitt was in the compare set.

**Likely causes (verify):**
1. **Per-column figure pool not isolated** — `loadCompareView()` / `renderCompareColumn()` may share gallery state or pull figures from wrong column when opening lightbox.
2. **Weak relevance filter** — `filterByQueryRelevance` on compare column figures uses query text but not strict entity/tag lock; cross-root leakage (same as B8 root-narrow issue).
3. **Retrieval fan-out** — each compare entity runs full topic-page retrieval (3–4 query variants × 5 sources); off-topic cards/figures can enter the pool.
4. **No entity guard on DDx/compare adds** — user can add unrelated VS targets; compare synthesis then juxtaposes unrelated diagnoses (expected) but **images must stay per-column**.

**Fix direction:**
- Bind lightbox `currentGallery` to **the column index** that launched it.
- Post-filter each compare column’s `figures`/`cards` by that column’s `tag` root + entity label before display.
- In compare prompt, pass only that column’s evidence to image picker (never global merged pool).
- Optional: warn when compare set spans unrelated roots.

**Files:** `static/app.js` (`loadCompareView`, `renderCompareColumn`, `bindPreviewHandlers`, `openMediaPreview`), `app.py` (`api_compare`).

---

## 2. Compare table renders as raw ` ```markdown ` fence (tables “not working”)

**What user saw:** AI Comparison Analysis shows literal:

```markdown
| Feature | Burkitt Lymphoma | ...
```

instead of an HTML `<table>`.

**Root cause:** `renderMarkdown()` in `app.js` does **not** strip fenced code blocks before parsing. Model wrapped the table in ` ```markdown ... ``` `. `isMarkdownTable()` never runs on fenced content → rendered as `<p>` with backticks.

**Fix direction:**
- In `renderMarkdown`, detect opening fence (` ``` ` optional lang) and:
  - If inner content is a pipe table → `renderMarkdownTable(inner)`
  - Else render as `<pre>` or strip fences and re-parse
- Add unit test: fenced markdown table → `<table class="answer-table">`

**Files:** `static/app.js` (`renderMarkdown`, `isMarkdownTable`).

---

## 3. Redundant Browse subcategories (HN especially)

**What user saw:** HN chevron list has overlapping pairs:
- `Salivary` (31) + `Salivary_Gland` (47)
- `Oral` (15) + `Oral_Cavity` (19)
- `Odontogenic` (22) + `Odontogenic_Maxillofacial` (56)
- `Neck` (7) + `Neck_Lymph_Node` (9)
- `Neuroendocrine` (2) + `Neuroendocrine_Paraganglioma` (6)
- `Ear` (12) + `Ear_Temporal_Bone` (22)
- etc.

**Root cause:** Browse index uses **2nd path segment** as subcategory label with **no alias/lump map**. ABPath/WHO tags use inconsistent granularity (`Salivary` vs `Salivary_Gland`).

**Not the same as A0 cyto lumping** — needs a new **`browse_subcategory_alias_map`** or index rebuild rule (e.g. `Salivary` → `Salivary_Gland`, `Oral` → `Oral_Cavity`). **Gate on user approval** like A0.

**Measured:** HN has **27** subcategories in `static/browse_tag_index_v0_1.json`.

**Files:** `scripts/build_browse_tag_index_v0_1.py`, optional `outputs/.../browse_subcategory_alias_map_v0_1.json`.

---

## 4. PathOut → Pathoutlines — ONLY PARTIALLY FIXED

**User says:** “we never fixed pathout to pathoutlines”

**What IS fixed (commit `8c96f92`):**
- `SOURCE_LABELS.pathout = "Pathoutlines"` → citation **badge** in Sources & citations (user screenshot shows blue **Pathoutlines** badge ✓)
- `app.py` `_SOURCE_LABELS["pathout"] = "Pathoutlines"` → synthesis citation index for **new** live pages
- `prompts.py` example link text `Pathoutlines`

**What is NOT fixed:**
| Surface | Still wrong |
|---------|-------------|
| Prebuilt `answer_markdown` | Inline links still `[PathOut](url)` — baked at prebuild time |
| Prebuilt inline textbook links | `[Hn Atlas]`, `[Hn Gnepp]`, `[Cyto Pattern]` from synthesis, not `citationSourceLabel` |
| `index.html` subtitle | Still says “PathOut” |
| Notes placeholder | Still says “PathOut pages” |
| Citation `tag-chip` | Shows raw `primary_tag` path (e.g. long `HN::...::`) — not a display issue for PathOut name but looks noisy |
| Synthesis prompt enforcement | Model can still emit `[PathOut]` unless post-processed |

**Fix direction:**
1. **Post-process rendered markdown** — replace link labels `[PathOut]` → `[Pathoutlines]`; map `[Hn Atlas]` → `[Atlas]`, `[Hn Gnepp]` → `[Gnepp]` via alias table (mirror `TEXTBOOK_ALIASES` + root strip).
2. **Re-prebuild pilot pages** after prompt/label fixes OR run a markdown normalizer on cache JSON.
3. Update `index.html` subtitle + placeholders.

**Files:** `static/app.js` (`inlineMarkdown` / link label normalizer), `prompts.py`, `static/index.html`, optional `scripts/normalize_prebuild_markdown_v0_1.py`.

---

## 5. Textbook labels: HN_Atlas → Atlas, hn_gnepp → Gnepp — ONLY ON CITATION BADGE

**What IS fixed:** `textbookLabel(source_id)` + `citationSourceLabel()` strips root prefix for **citation card badge** when `card.source === "textbooks"`.

**What user still sees:**
- Inline answer text: `[Hn Atlas](url)`, `[Hn Gnepp](url)` in topic body (prebuild + live synthesis).
- Compare modal caption: `Serous cystadenoma | Serous cystadenoma | https://...` (caption format issue).

**Fix direction:** Same as §4 — normalize **inline markdown link text** in `inlineMarkdown()` using:
```js
// Pseudocode: [Hn Gnepp](url) → [Gnepp](url)
// [PathOut](url) → [Pathoutlines](url)
```
Apply to `renderMarkdown` / `inlineMarkdown` output, not just badges.

**Files:** `static/app.js` (`inlineMarkdown`, `TEXTBOOK_ALIASES`).

---

## 6. Videos on Pleomorphic Adenoma — retrieved but unusable and duplicated

**User:** “i dont see video cards on pleomorphic adenoma — its just in the hidden refs”

**Measured on prebuild** `HN__Salivary_Gland__Benign_Tumor__Pleomorphic_Adenoma.json`:
- **7 video cards**, ALL same title: `Benign Cystic Neck Mass (Case 01)`
- **Same `video_id`:** `gcs_gs_pathology_hub_02_normalized_lectures_lecture_chunks`
- **Different `primary_tag`** on chunks (3× pleomorphic adenoma HN, 3× cyto salivary PA, 1× other) — **7 lecture chunks, 1 parent video**
- **`video_url` / `video_time_url`:** `null` on every card → **no playable link**

**UI gaps:**
1. No **Videos** strip on topic page (only “Selected Images” gallery from `figures[]`).
2. Videos only appear in collapsed **Sources & citations**.
3. **No dedupe** — same lecture repeated 7× because each chunk is a separate card.

**Fix direction:**
1. **UI:** Add `renderTopicVideos(cards)` section under Key Facts / beside gallery — dedupe by `video_id` or `title`, show timestamp range if `start_sec`/`end_sec` exist; disable link if URL null with honest “timestamp link not available”.
2. **Data/backend:** Fix lecture→`video_url` join (`raw_source_join_basis: no_match` in local lecture JSONL). UI cannot invent URLs.
3. **Dedupe in `renderCitations` or server** — collapse video cards sharing `video_id` + show chunk count.

**Files:** `static/app.js` (`renderTopicPage`, `renderCitations`), `app.py` (optional dedupe), backend lecture pipeline (out of MVP scope but document).

---

## 7. WSI (user zip — deferred)

User attached `WSI_Links_Project-20260711T140732Z-2-001.zip` (Rosai/Leeds/DPA/MGH tokens + tags). Not integrated. See prior session notes. Stage as sidecar + tag match for “Open WSI” links — **separate workstream**, do not touch curriculum SQLite.

---

## Suggested fix order (next agent)

| Priority | Item | Effort |
|----------|------|--------|
| P0 | Strip ` ```markdown ` fences so compare tables render | Small |
| P0 | Compare column figure isolation (no cross-entity lightbox) | Medium |
| P1 | Inline link label normalizer (Pathoutlines, Atlas, Gnepp) | Small |
| P1 | Topic page **Videos** strip + dedupe by `video_id` | Medium |
| P1 | `index.html` subtitle PathOut → Pathoutlines | Trivial |
| P2 | HN subcategory alias map + index rebuild (user gate) | Medium |
| P2 | Re-prebuild pilot pages OR normalize cached markdown | Batch job |
| P3 | Backend `video_url` join fix | Backend/data |

---

## Verification checklist

- [ ] Compare 4 unrelated entities → each column’s images only in that column’s lightbox
- [ ] Compare AI table renders as HTML table, not fenced raw markdown
- [ ] Pleomorphic Adenoma → visible **Videos** section; ≤1 row per `video_id`; honest message if URL null
- [ ] Topic page inline links show **Pathoutlines**, **Atlas**, **Gnepp** (not PathOut / Hn Atlas / Hn Gnepp)
- [ ] Citation badges still show Pathoutlines / journal names / stripped textbook names
- [ ] HN browse: no duplicate Salivary/Salivary_Gland after alias map (post-rebuild)

---

## Do NOT

- Touch curriculum SQLite, figure-quality sidecar, or unrelated WIP (`figure_quality_filter.py` unstaged)
- Claim video works end-to-end until `video_url` or `video_time_url` is non-null on live API probe
- Rebuild browse index for subcategory aliases without user sign-off on alias map
