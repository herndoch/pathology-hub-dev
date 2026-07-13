# Handoff — BM Intro Contextual Cloze Anki Builder (v0_1)

Date: 2026-07-13  
Audience: another AI (or human) building the Heme SH **BM Intro** contextual-cloze deck  
**Read first:** `docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md` (shared SOP rules, exclusions, tag law)  
Index: `docs/HANDOFF_HEME_SH_ANKI_BUILDER_INDEX_v0_1.md`

---

## Purpose

Build an image-grounded, source-aligned contextual cloze Anki deck for **Heme SH BM Intro**, following the TNK Lymphomas exemplar and Contextual Cloze SOP v1.1.

This series handoff supplies **paths, counts, layout, download commands, and a paste-ready brief**. Shared authoring/QA rules live in the COMMON doc.

### Series-specific note — HIGH YIELD despite 0 gated chunks

`chunks_indexable.jsonl` is **intentionally empty** because semantic gates treat this as a survey/methods talk (low match to disease-entity leaves). That is a **chat/retrieval filter**, not a teaching judgment.

This lecture is **high yield**. Scale (from manifest): ~52 min, **700** transcript segments, **47** frames, all frames present in the asset library. Content emphasis includes bone marrow interpretation approach, aspirate vs biopsy roles, adequacy/useless samples, cellularity, lineage topography, low-power screening, and pitfalls.

**Builder rules for this series:**

1. Scope **only** from `lecture_index.json` + `transcript.txt` + `frames.jsonl` (+ `segments.jsonl` for timestamps).
2. Treat approach / methods / pitfall pearls as first-class cards — do not require a neat WHO neoplasm entity for every note.
3. When no disease entity applies, use a **lecture-aligned shared back** (SOP §6) and only an *exact* accepted tag if one exists; **ask before inventing tags**.
4. Prefer fewer high-yield pearls over a slide-by-slide dump; still do not abandon the lecture because chunks are empty.
5. ChatGPT paste template: `docs/HANDOFF_CHATGPT_HEME_ANKI_PROMPTS_v0_1.md` (BM Intro section).

---

## Attachment bundle (this series)

Attach everything in COMMON (TNK exemplar + SOP PDF + WHO heme JSON), plus:

### Lecture ZIPs

- `Heme_SH_BM_Intro_package.zip`

### Sidecars (per lecture)

For each lecture folder: `manifest.json`, `frames.jsonl`, `segments.jsonl`, and optionally `chunks_indexable.jsonl`.

**Gated chunk warning:** **0** gated chunks. That means “do not use chunks for scope,” **not** “thin lecture.” Always read full transcript, lecture index, and frames.

### Do not attach

`tag_audit.json`, `chunk_audit.json`, `audit.json` (see COMMON).

---

## GCS paths (verified 2026-07-13)

### ZIPs

```text
gs://pathology_hub/Heme_SH_BM_Intro_package.zip
```

### Sidecars

```text
gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_bm_intro_v0_1/
```

### Counts

| Part | Segments | Frames | Gated chunks |
|------|----------|--------|--------------|
| Lecture | 700 | 47 | 0 |

---

## Project layout

```text
heme_sh_bm_intro_deck_project/
├── SOP/
│   └── Pathology_Anki_Contextual_Cloze_SOP.pdf
├── style/
│   └── Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip
├── who/
│   └── WHO_WHO_JSON_PROCESSED_HEME.json
├── accepted_tags.json
├── lecture_1/
│   ├── Heme_SH_BM_Intro_package.zip
│   ├── manifest.json
│   ├── frames.jsonl
│   ├── segments.jsonl
│   └── chunks_indexable.jsonl
```

---

## Download script

```bash
BUNDLE=./heme_sh_bm_intro_deck_project
mkdir -p "$BUNDLE"/{SOP,style,who,lecture_1}

# Local/Drive: TNK exemplar zip → style/; WHO JSON → who/; SOP PDF → SOP/;
# Extract accepted_tags.json from TNK zip → $BUNDLE/accepted_tags.json

gsutil cp "gs://pathology_hub/Heme_SH_BM_Intro_package.zip" "$BUNDLE/lecture_1/"

gsutil -m cp \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_bm_intro_v0_1/manifest.json" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_bm_intro_v0_1/frames.jsonl" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_bm_intro_v0_1/segments.jsonl" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_bm_intro_v0_1/chunks_indexable.jsonl" \
  "$BUNDLE/lecture_1/"
```

---

## Paste-ready builder brief

```text
Build a contextual-cloze Anki deck for Heme SH BM Intro
(Introduction to Bone Marrow Interpretation — HIGH YIELD survey/methods talk).

STYLE AUTHORITY
- Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip
- Pathology_Anki_Contextual_Cloze_SOP.pdf (v1.1)
Follow the SOP and exemplar. Accepted-tag JSON inside the TNK package is the ONLY tag authority.

ENTITY / OUTLINE AUTHORITY
- WHO_WHO_JSON_PROCESSED_HEME.json when a disease entity is truly taught
- Otherwise lecture-aligned shared backs for approach/methods topics (SOP §6)

LECTURE CONTENT (scope authority — MANDATORY)
Heme_SH_BM_Intro_package.zip
Use transcript.txt, lecture_index.json, transcript_segments.json, and frames/
as the ONLY syllabus. chunks_indexable.jsonl has 0 rows — IGNORE for scope.
Do not refuse or shrink the deck because gated chunks are empty.
Preserve lecturer emphasis: adequacy, aspirate vs biopsy, cellularity, lineage
topography, low-power screening, pitfalls. Do not expand into an off-syllabus
WHO disease encyclopedia.

ALIGNMENT AIDS
- frames.jsonl (47) — front-image selection; image–timestamp–transcript alignment
- segments.jsonl (700) — exact ASR windows
- manifest.json — identity, counts, video URL, known limitations

DO NOT USE FOR TAGS OR SCOPE
- tag_audit.json, chunk_audit.json, audit.json, chunks_indexable.jsonl
- primary_tag on frames.jsonl

CARD RULES — docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md
Never invent tags; ask if no accepted tag fits an approach pearl.

DELIVERABLES
APKG, QA CSV, card inventory CSV, shared_backs.json, builder script,
accepted-tag authority, templates/CSS, package ZIP.
Prefer a smaller coherent HIGH-YIELD deck over a mechanical slide dump.

WORKFLOW
1) Validate sources + load accepted tags
2) Source spine from lecture index + transcript + frames.jsonl
3) Propose card inventory table for approval (topic | pearl | tag | frame time)
4) After approval: fronts → one-token clozes → shared backs → images → QA
```

---

## Known limitations

1. TNK exemplar + WHO heme JSON must be supplied from local/Drive (not under those names on GCS at audit time).
2. Gated chunks are sparse by design; not syllabus coverage.
3. Frame/chunk `primary_tag` values are semantic browse labels, not Anki accepted tags.
4. This handoff does not claim the deck is built, chat-indexed, vectorized, or API-exposed.
