# Handoff — PT-LPD (Post-Transplant LPD) Contextual Cloze Anki Builder (v0_1)

Date: 2026-07-13  
Audience: another AI (or human) building the Heme SH **PT-LPD (Post-Transplant LPD)** contextual-cloze deck  
**Read first:** `docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md` (shared SOP rules, exclusions, tag law)  
Index: `docs/HANDOFF_HEME_SH_ANKI_BUILDER_INDEX_v0_1.md`

---

## Purpose

Build an image-grounded, source-aligned contextual cloze Anki deck for **Heme SH PT-LPD (Post-Transplant LPD)**, following the TNK Lymphomas exemplar and Contextual Cloze SOP v1.1.

This series handoff supplies **paths, counts, layout, download commands, and a paste-ready brief**. Shared authoring/QA rules live in the COMMON doc.

---

## Attachment bundle (this series)

Attach everything in COMMON (TNK exemplar + SOP PDF + WHO heme JSON), plus:

### Lecture ZIPs

- `Heme_SH_PT_LPD_package.zip`

### Sidecars (per lecture)

For each lecture folder: `manifest.json`, `frames.jsonl`, `segments.jsonl`, and optionally `chunks_indexable.jsonl`.

**Gated chunk warning:** **16** gated chunks. Use as an index only — **not** syllabus/card-scope authority. Always read full transcript, lecture index, and frames.

### Do not attach

`tag_audit.json`, `chunk_audit.json`, `audit.json` (see COMMON).

---

## GCS paths (verified 2026-07-13)

### ZIPs

```text
gs://pathology_hub/Heme_SH_PT_LPD_package.zip
```

### Sidecars

```text
gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_pt_lpd_v0_1/
```

### Counts

| Part | Segments | Frames | Gated chunks |
|------|----------|--------|--------------|
| Lecture | 446 | 27 | 16 |

---

## Project layout

```text
heme_sh_pt_lpd_deck_project/
├── SOP/
│   └── Pathology_Anki_Contextual_Cloze_SOP.pdf
├── style/
│   └── Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip
├── who/
│   └── WHO_WHO_JSON_PROCESSED_HEME.json
├── accepted_tags.json
├── lecture_1/
│   ├── Heme_SH_PT_LPD_package.zip
│   ├── manifest.json
│   ├── frames.jsonl
│   ├── segments.jsonl
│   └── chunks_indexable.jsonl
```

---

## Download script

```bash
BUNDLE=./heme_sh_pt_lpd_deck_project
mkdir -p "$BUNDLE"/{SOP,style,who,lecture_1}

# Local/Drive: TNK exemplar zip → style/; WHO JSON → who/; SOP PDF → SOP/;
# Extract accepted_tags.json from TNK zip → $BUNDLE/accepted_tags.json

gsutil cp "gs://pathology_hub/Heme_SH_PT_LPD_package.zip" "$BUNDLE/lecture_1/"

gsutil -m cp \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_pt_lpd_v0_1/manifest.json" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_pt_lpd_v0_1/frames.jsonl" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_pt_lpd_v0_1/segments.jsonl" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_pt_lpd_v0_1/chunks_indexable.jsonl" \
  "$BUNDLE/lecture_1/"
```

---

## Paste-ready builder brief

```text
Build a contextual-cloze Anki deck for Heme SH PT-LPD (Post-Transplant LPD).

STYLE AUTHORITY
- Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip
- Pathology_Anki_Contextual_Cloze_SOP.pdf (v1.1)
Follow the SOP and exemplar. Accepted-tag JSON inside the TNK package is the ONLY tag authority.

ENTITY AUTHORITY
- WHO_WHO_JSON_PROCESSED_HEME.json

LECTURE CONTENT (scope authority)
Heme_SH_PT_LPD_package.zip
Use transcript.txt, lecture_index.json, transcript_segments.json, and frames/
as the primary teaching source. Lecture defines syllabus; WHO organizes shared backs.
Do not silently introduce off-syllabus cards.

ALIGNMENT AIDS (per lecture)
- frames.jsonl — front-image selection; image–timestamp–transcript alignment
- segments.jsonl — exact ASR windows when lecture index is weak
- manifest.json — identity, counts, video URL, known limitations

OPTIONAL INDEX (not scope)
- chunks_indexable.jsonl — navigation only (16 gated chunk(s) for this series).
  Do NOT define card scope from it.

DO NOT USE FOR TAGS OR SCOPE
- tag_audit.json, chunk_audit.json, audit.json
- primary_tag on frames.jsonl / chunks_indexable.jsonl

CARD RULES — follow docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md
(diagnosis visible/bold; one-token clozes; Tier-1 image match; byte-identical shared back
per PrimaryTag; two-column tap-to-expand gallery; exact accepted tags only).

DELIVERABLES
APKG, QA CSV, card inventory CSV, shared_backs.json, builder script,
accepted-tag authority, templates/CSS, package ZIP.
Prefer a smaller coherent deck over a large mechanical deck.

WORKFLOW
1) Validate sources + load accepted tags
2) Source spine from lecture index + transcript (+ frames.jsonl / segments.jsonl)
3) Draft fronts → one-token clozes
4) Shared backs from WHO → front images → entity galleries
5) Hard-fail QA → repair → rebuild APKG
```

---

## Known limitations

1. TNK exemplar + WHO heme JSON must be supplied from local/Drive (not under those names on GCS at audit time).
2. Gated chunks are sparse by design; not syllabus coverage.
3. Frame/chunk `primary_tag` values are semantic browse labels, not Anki accepted tags.
4. This handoff does not claim the deck is built, chat-indexed, vectorized, or API-exposed.
