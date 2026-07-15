# Handoff — Heme SH Contextual Cloze Anki Builder (COMMON v0_1)

Date: 2026-07-13  
Audience: any AI/human building a Heme SH contextual-cloze Anki deck  
Style law: Pathology Anki Contextual Cloze SOP v1.1 + TNK exemplar package

Use this document for **shared rules**. Each lecture series has a sibling handoff under `docs/HANDOFF_*_ANKI_BUILDER_v0_1.md` with series-specific paths, counts, and a paste-ready brief. Index: `docs/HANDOFF_HEME_SH_ANKI_BUILDER_INDEX_v0_1.md`.

---

## Shared attachment types

| Role | File | Notes |
|------|------|-------|
| Style authority | `Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip` | SOP exemplars, templates, **accepted-tag JSON**, QA, shared-back examples, builder, schemas |
| Rule contract | `Pathology_Anki_Contextual_Cloze_SOP.pdf` (v1.1) | Attach with the exemplar |
| Entity canon | `WHO_WHO_JSON_PROCESSED_HEME.json` | Morphology, phenotype, molecular, DDx, prognosis, WHO tags, figures |
| Raw lecture | `Heme_SH_<Topic>_package.zip` (per lecture) | `transcript.txt`, `transcript_segments.json`, `lecture_index.json`, `frames/` |
| Package map | `manifest.json` (per lecture) | Counts, duration, video URL, limitations |
| Image–time alignment | `frames.jsonl` (per lecture) | Timestamp, transcript context, image URL, `video_time_url` |
| Fine ASR windows | `segments.jsonl` (per lecture) | When lecture index is weak |
| Optional index | `chunks_indexable.jsonl` (per lecture) | Navigation only — **never** card-scope authority |

### Do not attach

| File | Why |
|------|-----|
| `tag_audit.json` | Competing/legacy/malformed tag namespaces |
| `chunk_audit.json` | Pipeline provenance |
| `audit.json` | Pipeline provenance |

**Tag authority is singular:** accepted-tag JSON inside the TNK exemplar only. Ignore `primary_tag` on `frames.jsonl` / `chunks_indexable.jsonl` for permitted tags (semantic retrieval labels, not deck law).

### GCS builder prefix (2026-07-13)

```text
gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/
```

| Object | Status |
|--------|--------|
| `shared/Pathology_Anki_Contextual_Cloze_SOP_v1_1.pdf` | on GCS |
| `shared/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip` | **pending laptop upload** |
| `shared/WHO_WHO_JSON_PROCESSED_HEME.json` | **pending laptop upload** |
| `shared/accepted_tags.json` | **pending** (extract from TNK zip) |
| `docs/` + `series_index.json` | on GCS (handoffs + pointers to lecture ZIPs/sidecars) |

Publish / drop instructions: `docs/PLAN_HEME_ANKI_BUILDER_GCS_BUNDLE_v0_1.md`  
Also: `gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/DROPBOX_FOR_LOCAL_UPLOADS.md`

### Optional histology download

```text
gs://pathology-hub-0/_asset_library/lectures/Heme_SH_<Stem>/
```

Otherwise `image_url` in `frames.jsonl` is enough for link-based cards.

---

## SOP ↔ pipeline mapping

| SOP expects | Pipeline equivalent |
|-------------|---------------------|
| `lecture_N/manifest.json` | deck sidecar `manifest.json` |
| `lecture_N/chunks.jsonl` | `chunks_indexable.jsonl` (often sparse) |
| `lecture_N/frames_index.jsonl` | `frames.jsonl` |
| `lecture_N/frames/` | inside lecture ZIP |
| Raw ASR support | `segments.jsonl` |
| `canonical_reference.json` | `WHO_WHO_JSON_PROCESSED_HEME.json` |
| `accepted_tags.json` | from TNK exemplar only |

### Universal scope override

SOP §2 says curated chunks are the teaching grain for videos. Across Heme SH, gated `chunks_indexable.jsonl` is intentionally sparse (semantic usefulness gates). **Override for all Heme SH decks:**

> **Teaching grain** = `transcript.txt` + `lecture_index.json` (+ `segments.jsonl` for timestamps).  
> **`chunks_indexable.jsonl`** = navigation hint only.

Lecture defines syllabus; WHO organizes shared entity backs. Do not silently introduce off-syllabus cards.

---

## Non-negotiable rules (SOP v1.1)

### Card front

- Diagnosis **visible and bold**; never cloze the diagnosis.
- One natural contextual sentence (not `Entity: fact`).
- Cloze feature / marker / mechanism / pattern / differential / pitfall / clinical implication.
- Put the key contrast or significance in the **same** sentence.
- **One-token clozes**; multi-word concepts → multiple `{{c1::…}}` (still one Anki card).
- Cloze syntax red+bold; italicize gene symbols/fusions; IHC markers roman unless discussing the gene.

### Images

| Tier | Use |
|------|-----|
| 1 | Direct evidence (CD30 cloze → actual CD30 stain) |
| 2 | Disease-context image when fact is not visible |
| 3 | No image (better than unrelated) |

Crop answer-leaking labels; front caption must not reveal answer; full source image stays in back gallery; record alignment rationale in QA.

### Shared back (one per exact PrimaryTag)

Byte-identical `BackContextHTML` for every note with the same tag. Prefer WHO entity entry; 1–3 bullets per section:

1. Definition  
2. Morphology  
3. Phenotype  
4. Molecular  
5. Clinical / Distribution  
6. Key differential / Pitfall  

Do not dump per-card teaching notes on the back.

### Gallery

- Two-column tap-to-expand (`<details class="image-toggle">`) after shared back.
- Captions hidden until tap; no filenames.
- One column at ≤600 px.
- Deduplicate lecture + WHO images per entity.

### Tags

- Load accepted-tag JSON **before** writing cards.
- Exact full tags only; one `PrimaryTag` per note.
- No source / lecture / timestamp / workflow tags.

### Hard-fail QA

Diagnosis missing/hidden/prefixed; multi-token cloze; front depends on separate teaching notes; tag not exact; unrelated/leaking image; IHC without actual stain; differing shared backs for same tag; visible captions; gallery not two-wide at standard width; malformed cloze.

### Required deliverables

`.apkg`, QA CSV, card inventory CSV, `shared_backs.json`, builder script, accepted-tag authority, templates/CSS, package ZIP.  
Prefer a smaller coherent deck over a large mechanical deck.

---

## Production sequence

1. Validate sources; copy `accepted_tags.json` from TNK exemplar.  
2. Source spine from lecture index + transcript (`frames.jsonl` / `segments.jsonl`).  
3. Draft contextual fronts for taught entities.  
4. Enforce one-token clozes.  
5. Shared backs from WHO (one per tag).  
6. Front images via `frames.jsonl`.  
7. Deduplicated entity galleries.  
8. Emit QA / inventory / shared_backs / builder / APKG.  
9. Hard-fail QA → repair → rebuild.

---

## Generic download pattern

```bash
SERIES=<slug>   # e.g. aml
STEM=<Heme_SH_Stem>  # e.g. Heme_SH_AML
PKG=<package_id>     # e.g. heme_sh_aml_v0_1
BUNDLE=./heme_sh_${SERIES}_deck_project
mkdir -p "$BUNDLE"/{SOP,style,who,lecture_1}

# Local/Drive stash:
# cp TNK zip → $BUNDLE/style/
# cp WHO_WHO_JSON_PROCESSED_HEME.json → $BUNDLE/who/
# cp SOP PDF → $BUNDLE/SOP/
# Extract accepted_tags.json from TNK zip → $BUNDLE/accepted_tags.json

gsutil cp "gs://pathology_hub/${STEM}_package.zip" "$BUNDLE/lecture_1/" \
  || gsutil cp "gs://pathology_hub/${STEM}_chatgpt_readable_package.zip" "$BUNDLE/lecture_1/"

gsutil -m cp \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/${PKG}/manifest.json" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/${PKG}/frames.jsonl" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/${PKG}/segments.jsonl" \
  "gs://pathology_hub/02_normalized/lectures/deck_packages/${PKG}/chunks_indexable.jsonl" \
  "$BUNDLE/lecture_1/"
```

Multi-part series: use `lecture_1/`, `lecture_2/`, … and one ZIP + sidecar set each. Series handoffs list exact paths.

---

## Workstream boundary

Keep Anki deck building separate from Evidence RAG, report-style RAG, HTML rendering, backend API, and Custom GPT frontend. Do not claim a deck is indexed, vectorized, tagged for chat, or API-exposed unless a separate audit/manifest proves it.

---

## Survey / methods lectures (e.g. BM Intro)

If `chunks_indexable.jsonl` is empty or tiny, that is a **semantic gate artifact** (weak match to disease leaves), not proof the talk is low-yield. Still build from transcript + lecture index + frames. Prefer approach/pitfall pearls; use lecture-aligned shared backs when no WHO disease entity applies (SOP §6); never invent tags.

ChatGPT paste templates: `docs/HANDOFF_CHATGPT_HEME_ANKI_PROMPTS_v0_1.md`.

---

## Related

- `docs/HANDOFF_HEME_SH_ANKI_BUILDER_INDEX_v0_1.md`
- `docs/HANDOFF_CHATGPT_HEME_ANKI_PROMPTS_v0_1.md`
- `docs/PLAN_HEME_SH_DECK_PACKAGE_BATCH_v0_1.md`
- `docs/METHODS_LECTURE_DECK_CHUNKING_v0_1.md`
