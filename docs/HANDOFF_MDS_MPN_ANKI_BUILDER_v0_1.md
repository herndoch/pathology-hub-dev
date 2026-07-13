# Handoff — MDS/MPN Contextual Cloze Anki Builder (v0_1)

Date: 2026-07-13  
Audience: another AI (or human) building the Heme SH MDS/MPN contextual-cloze deck  
Style law: Pathology Anki Contextual Cloze SOP v1.1 + TNK exemplar package

---

## Purpose

Build an image-grounded, source-aligned contextual cloze Anki deck for **Heme SH MDS/MPN lectures 1–3**, following the established TNK Lymphomas exemplar and the Contextual Cloze SOP.

This handoff defines:

1. Which files to attach to the card-building AI
2. File-name mapping (SOP layout ↔ GCS pipeline)
3. Scope override for sparse gated chunks
4. Non-negotiable authoring / QA rules (from SOP)
5. Download commands for GCS-backed inputs
6. Paste-ready builder brief

---

## Best attachment bundle

### Essential (eight types; sidecars are per lecture)

| # | File | Role |
|---|------|------|
| 1 | `Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip` | Style authority: SOP exemplars, templates, **accepted-tag JSON**, QA files, shared-back examples, builder, schemas |
| 2 | `WHO_WHO_JSON_PROCESSED_HEME.json` | Canonical entity definitions: morphology, phenotype, molecular, DDx, prognosis, WHO tags, figure legends/URLs |
| 3–5 | `Heme_SH_MDS_MPN_{1,2,3}_package.zip` | Raw teaching source: `transcript.txt`, `transcript_segments.json`, `lecture_index.json`, `frames/` |
| 6 | `manifest.json` (×3) | Package map: identity, counts, duration, video URL, asset prefix, limitations |
| 7 | `frames.jsonl` (×3) | Image–time alignment: timestamp, transcript context, image path/URL, `video_time_url` |
| 8 | `segments.jsonl` (×3) | Exact ASR windows when lecture index is imperfect |

### Optional ninth (with explicit warning)

| File | Role |
|------|------|
| `chunks_indexable.jsonl` (×3) | Navigation / provisional entity windows only |

**Warning:** Current gated indices are sparse (MDS/MPN 1 = **5** chunks, 2 = **5**, 3 = **7**; **17 total**). Use as an index, **not** as complete lecture content or card-scope authority. Always inspect full transcript, lecture index, and frames.

### Do **not** attach

| File | Why |
|------|-----|
| `tag_audit.json` | Pipeline debug; duplicate/legacy/malformed competing tag namespaces |
| `chunk_audit.json` | Pipeline provenance, not teaching source |
| `audit.json` | Pipeline provenance |

**Tag authority is singular:** accepted-tag JSON inside the TNK exemplar package only. Ignore `primary_tag` on `frames.jsonl` / `chunks_indexable.jsonl` for permitted tags — those are semantic retrieval tags, not deck law.

### SOP PDF (strong add-on)

Attach `Pathology_Anki_Contextual_Cloze_SOP.pdf` (v1.1) alongside the TNK zip.  
- Exemplar = finished examples and package scaffolding  
- SOP = rule contract the exemplar implements

---

## GCS-verified paths (2026-07-13)

### Lecture ZIPs (bucket root)

```text
gs://pathology_hub/Heme_SH_MDS_MPN_1_package.zip
gs://pathology_hub/Heme_SH_MDS_MPN_2_package.zip
gs://pathology_hub/Heme_SH_MDS_MPN_3_package.zip
```

### Sidecars (per lecture)

```text
gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_mds_mpn_1_v0_1/
gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_mds_mpn_2_v0_1/
gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_mds_mpn_3_v0_1/
```

Useful files in each sidecar folder:

- `manifest.json`
- `frames.jsonl`
- `segments.jsonl`
- `chunks_indexable.jsonl` (optional)

Exclude: `tag_audit.json`, `chunk_audit.json`, `audit.json`, empty `segments_indexable.jsonl`.

### Scale (from manifests / live download)

| Lecture | Segments | Frames | Gated chunks |
|---------|----------|--------|--------------|
| MDS/MPN 1 | 703 | 56 | 5 |
| MDS/MPN 2 | 817 | 46 | 5 |
| MDS/MPN 3 | 917 | 67 | 7 |

### Not on GCS under these names

Supply from local/Drive stash:

- `Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip`
- `WHO_WHO_JSON_PROCESSED_HEME.json`
- Contextual Cloze SOP PDF/DOCX/Markdown (if not already inside TNK package)

### Optional image download (if AI must open histology, not just URLs)

```text
gs://pathology-hub-0/_asset_library/lectures/Heme_SH_MDS_MPN_1/
gs://pathology-hub-0/_asset_library/lectures/Heme_SH_MDS_MPN_2/
gs://pathology-hub-0/_asset_library/lectures/Heme_SH_MDS_MPN_3/
```

Otherwise `image_url` in `frames.jsonl` is enough for link-based cards.

---

## Recommended project layout

Sidecars are **per lecture**, not single merged files:

```text
mds_mpn_deck_project/
├── SOP/
│   └── Pathology_Anki_Contextual_Cloze_SOP.pdf
├── style/
│   └── Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip
├── who/
│   └── WHO_WHO_JSON_PROCESSED_HEME.json
├── accepted_tags.json                    # copied from TNK zip only
├── lecture_1/
│   ├── Heme_SH_MDS_MPN_1_package.zip     # or extracted contents
│   ├── manifest.json
│   ├── frames.jsonl
│   ├── segments.jsonl
│   └── chunks_indexable.jsonl            # optional index
├── lecture_2/ ...
└── lecture_3/ ...
```

---

## SOP ↔ pipeline file mapping

| SOP expects | MDS/MPN equivalent |
|-------------|-------------------|
| `lecture_N/manifest.json` | `lecture_N/manifest.json` from deck sidecar |
| `lecture_N/chunks.jsonl` | `chunks_indexable.jsonl` (**sparse — see override**) |
| `lecture_N/frames_index.jsonl` | `frames.jsonl` |
| `lecture_N/frames/` | inside each lecture ZIP |
| Raw ASR support | `segments.jsonl` |
| `canonical_reference.json` | `WHO_WHO_JSON_PROCESSED_HEME.json` |
| `accepted_tags.json` | from TNK exemplar zip only |
| `user_style_reference.docx` | templates / exemplar inside TNK zip |

### Scope override (MDS/MPN specific)

SOP §2: *“For videos, use curated chunks as the teaching grain.”*

For these three lectures, gated chunks are far too incomplete. **Override:**

> **Teaching grain** = `transcript.txt` + `lecture_index.json` (+ `segments.jsonl` for timestamp recovery).  
> **`chunks_indexable.jsonl`** = navigation hint only — never card-scope authority.

Everything else in the SOP applies unchanged.

---

## Non-negotiable rules (from SOP v1.1)

### Card front

- Diagnosis **visible and bold**; never cloze the diagnosis.
- One natural contextual sentence (not `Entity: fact`).
- Cloze the feature / marker / mechanism / pattern / differential / pitfall / clinical implication.
- Include the key contrast or significance in the **same** sentence.
- **One-token clozes**; multi-word concepts → multiple `{{c1::…}}` on the same note (still one Anki card).
- Cloze syntax red+bold; italicize gene symbols and fusions; IHC markers roman unless discussing the gene.

### Images

| Tier | Use |
|------|-----|
| 1 | Direct evidence (CD30 cloze → actual CD30 stain) |
| 2 | Disease-context image when fact is not directly visible |
| 3 | No image (preferable to unrelated/misleading) |

- Crop answer-leaking labels; front caption must not reveal answer.
- Keep complete source image in back gallery.
- Record image-alignment rationale in QA.

### Shared back (one per exact primary tag)

Byte-identical `BackContextHTML` for every note with the same tag. Prefer WHO entity entry; 1–3 bullets per section:

1. Definition  
2. Morphology  
3. Phenotype  
4. Molecular  
5. Clinical / Distribution  
6. Key differential / Pitfall  

Do **not** dump per-card teaching notes on the back.

### Gallery

- Two-column tap-to-expand (`<details class="image-toggle">`) after shared back.
- Captions hidden until tap/click; no filenames.
- Collapse to one column at ≤600 px.
- Deduplicate lecture + WHO images per entity.

### Tags

- Load accepted-tag JSON **before** writing cards.
- Exact full tags only; one `PrimaryTag` per note.
- No source / lecture / timestamp / workflow tags.

### Hard-fail QA

- Diagnosis missing, hidden, or mechanically prefixed  
- Multi-token cloze (unsplit)  
- Front depends on separate teaching notes  
- Tag not exact from accepted list  
- Unrelated / missing / answer-revealing front image  
- IHC question without actual stain image  
- Shared back differs among notes with same tag  
- Captions visible by default  
- Back gallery not two-wide at standard card width  
- Malformed cloze syntax  

### Required deliverables

- `.apkg` (one generated card per approved note)  
- QA CSV  
- Card inventory CSV  
- `shared_backs.json`  
- Reproducible builder script  
- Accepted-tag authority + card template/CSS  
- Package ZIP with non-source deliverables  

Prefer a smaller coherent deck over a large mechanical deck.

---

## Production sequence

1. Validate sources; copy `accepted_tags.json` from TNK exemplar.  
2. Build source spine from **lecture index + transcript** (`frames.jsonl` for frame overlap; `segments.jsonl` for fine windows).  
3. Draft high-yield contextual fronts per taught entity (lecture defines syllabus).  
4. Enforce one-token clozes.  
5. Build shared backs from WHO JSON (one per tag).  
6. Assign/crop front images via `frames.jsonl` (`image_url`, `video_time_url`, `transcript_context`).  
7. Build deduplicated entity galleries (lecture + WHO figures).  
8. Emit QA CSV, card inventory, `shared_backs.json`, builder script, APKG.  
9. Run hard-fail checks; repair before accepting.

---

## Download script (GCS portion)

```bash
BUNDLE=./mds_mpn_deck_project
mkdir -p "$BUNDLE"/{SOP,style,who,lecture_{1,2,3}}

# Style + WHO + SOP: attach manually from local/Drive stash
# cp /path/to/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip "$BUNDLE/style/"
# cp /path/to/WHO_WHO_JSON_PROCESSED_HEME.json "$BUNDLE/who/"
# cp /path/to/Pathology_Anki_Contextual_Cloze_SOP.pdf "$BUNDLE/SOP/"
# Extract accepted_tags.json from TNK zip into "$BUNDLE/accepted_tags.json"

gsutil -m cp \
  gs://pathology_hub/Heme_SH_MDS_MPN_1_package.zip \
  "$BUNDLE/lecture_1/"
gsutil -m cp \
  gs://pathology_hub/Heme_SH_MDS_MPN_2_package.zip \
  "$BUNDLE/lecture_2/"
gsutil -m cp \
  gs://pathology_hub/Heme_SH_MDS_MPN_3_package.zip \
  "$BUNDLE/lecture_3/"

for n in 1 2 3; do
  gsutil -m cp \
    gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_mds_mpn_${n}_v0_1/manifest.json \
    gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_mds_mpn_${n}_v0_1/frames.jsonl \
    gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_mds_mpn_${n}_v0_1/segments.jsonl \
    gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_mds_mpn_${n}_v0_1/chunks_indexable.jsonl \
    "$BUNDLE/lecture_${n}/"
done
```

---

## Paste-ready builder brief

```text
Build a contextual-cloze Anki deck for Heme SH MDS/MPN (lectures 1–3).

STYLE AUTHORITY
- Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip
- Pathology_Anki_Contextual_Cloze_SOP.pdf (v1.1)
Follow the SOP and exemplar: wording, templates, QA gates, shared-back pattern,
and accepted-tag JSON. No other tag source is valid.

ENTITY AUTHORITY
- WHO_WHO_JSON_PROCESSED_HEME.json
Morphology, phenotype, molecular, differentials, prognosis, WHO tags, figures.

LECTURE CONTENT (scope authority)
- Heme_SH_MDS_MPN_1_package.zip
- Heme_SH_MDS_MPN_2_package.zip
- Heme_SH_MDS_MPN_3_package.zip
Use transcript.txt, lecture_index.json, transcript_segments.json, and frames/
as the primary teaching source. Lecture defines what is taught; WHO organizes
shared entity backs only. Do not silently introduce off-syllabus cards.

ALIGNMENT AIDS
- frames.jsonl (per lecture): front-image selection; image–timestamp–transcript alignment
- segments.jsonl (per lecture): exact ASR windows when lecture index is weak
- manifest.json (per lecture): identity, counts, video URL, known limitations

OPTIONAL INDEX (not scope)
- chunks_indexable.jsonl — navigation only (17 gated chunks total across 3 lectures).
  Do NOT define card scope from it.

DO NOT USE FOR TAGS OR SCOPE
- tag_audit.json, chunk_audit.json, audit.json
- primary_tag on frames.jsonl / chunks_indexable.jsonl (retrieval tags, not deck law)

CARD RULES (non-negotiable)
- Diagnosis visible and bold; never cloze diagnosis
- One natural sentence; cloze feature/marker/mechanism/pitfall + significance in-sentence
- One-token clozes; split multiword concepts into multiple c1 deletions
- Front image = direct evidence (Tier 1) or disease context; crop leakage; no answer in caption
- One byte-identical shared WHO-derived back per exact PrimaryTag
- Two-column tap-to-expand entity gallery; captions hidden until tap
- Exact accepted tags only; one PrimaryTag per note; no meta tags

DELIVERABLES
- APKG, QA CSV, card inventory CSV, shared_backs.json, builder script,
  accepted-tag authority, templates/CSS, package ZIP
Prefer a smaller coherent deck over a large mechanical deck.

WORKFLOW
1) Validate sources + load accepted tags
2) Source spine from lecture index + transcript (+ frames.jsonl / segments.jsonl)
3) Draft fronts → enforce one-token clozes
4) Shared backs from WHO → front images → entity galleries
5) Hard-fail QA → repair → rebuild APKG
```

---

## Known limitations

1. TNK exemplar zip and WHO heme JSON were **not** found on `gs://pathology_hub` / `gs://pathology-hub-0` under the expected filenames at audit time — attach from local stash.  
2. Gated `chunks_indexable.jsonl` is intentionally sparse (semantic usefulness gates); it must not be treated as syllabus coverage.  
3. Frame `primary_tag` values are semantic browse labels (`semantic_heme_browse_v0_1`), not human-gold and not Anki accepted tags.  
4. This handoff does **not** claim the MDS/MPN deck is built, indexed for chat, or API-exposed.

---

## Related repo docs

- `docs/PLAN_HEME_SH_DECK_PACKAGE_BATCH_v0_1.md` — lecture deck package inventory  
- `docs/METHODS_LECTURE_DECK_CHUNKING_v0_1.md` — chatgpt_readable → sidecar methods  
- `docs/LECTURE_DECK_PACKAGE_POC_CHATGPT_READABLE_v0_1.md` — format POC  
