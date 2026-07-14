# ChatGPT paste prompts — Heme SH Contextual Cloze Anki (v0_1)

Date: 2026-07-13  
Repo: `herndoch/pathology-hub-dev`  
PR with handoffs: https://github.com/herndoch/pathology-hub-dev/pull/18

Use these in **ChatGPT with GitHub connected**. The handoffs tell the model *what law to follow*; you still attach the lecture/style/WHO files (ChatGPT cannot pull private GCS for you).

---

## Lazy alternative: Colab → a bunch of ChatGPT zips

Run this Colab (preferred):

`notebooks/Heme_SH_Anki_ChatGPT_Upload_Zips_v0_1.ipynb`

1. Put TNK zip + WHO JSON somewhere under MyDrive once.
2. Leave `SERIES_CHOICE = "ALL"` and `MODE = "light"`.
3. Runtime → Run all.
4. Open Drive → `MyDrive/Heme_Anki_ChatGPT_Zips/`.
5. Attach one `series_*_chatGPT_upload.zip` per ChatGPT chat; paste that zip’s `CHATGPT_PROMPT.txt`.

(Older assembler: `notebooks/Heme_SH_Anki_Builder_Drive_Bundle_Assembler_v0_1.ipynb`.)

**TNK** = T/NK-lymphomas **finished Anki exemplar** (style law), not the lecture you are converting.

---

## Before you start

1. **Merge PR #18** (or tell ChatGPT to open branch `cursor/mds-mpn-anki-handoff-9231`). GitHub connectors usually see `master` first.
2. **Prefer GCS shared prefix** (after you land TNK + WHO):
   `gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/`
   Until those two files are uploaded from your laptop, keep them on Drive and attach manually.
3. Lecture ZIP + sidecars: listed in `series_index.json` under that same builder prefix (pointers; not re-copied).
4. **Do not upload** `tag_audit.json`, `chunk_audit.json`, `audit.json`.
5. One deck series per ChatGPT conversation when possible.

---

## How “@github” fits

Pattern that usually works with ChatGPT + GitHub:

```text
@github herndoch/pathology-hub-dev

Open and follow these files:
- docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md
- docs/HANDOFF_<SERIES>_ANKI_BUILDER_v0_1.md
```

Then paste the series brief (below) and attach the upload bundle.

If `@github` is unavailable, paste the COMMON + series handoff markdown into the chat, or say: “Read PR #18 / branch `cursor/mds-mpn-anki-handoff-9231` docs.”

---

## Universal first message (paste once per new chat)

```text
@github herndoch/pathology-hub-dev

You are building a Pathology Anki contextual-cloze deck per our SOP.

Read FIRST (in order):
1) docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md
2) docs/HANDOFF_HEME_SH_ANKI_BUILDER_INDEX_v0_1.md
3) the series handoff I name in the next message

Hard rules:
- Style authority = TNK exemplar zip + Contextual Cloze SOP only.
- Tag authority = accepted-tag JSON inside the TNK exemplar ONLY.
- Lecture transcript + lecture_index define syllabus (NOT chunks_indexable.jsonl).
- Gated chunks are navigation only; zero or few chunks does NOT mean low-yield.
- Do NOT use tag_audit / chunk_audit / audit.json, and ignore primary_tag on frames/chunks for tagging.
- Prefer a smaller coherent deck over a mechanical deck.
- Deliverables: APKG (or buildable note TSVs + builder), QA CSV, card inventory CSV, shared_backs.json, builder script notes.

I will attach: TNK exemplar zip, SOP PDF, WHO_WHO_JSON_PROCESSED_HEME.json, lecture package zip(s), and usually frames.jsonl + segments.jsonl + manifest.json.

Acknowledge the SOP rules briefly, then wait for the series name and uploads.
```

---

## Per-series second message (fill SERIES)

Replace `SERIES` with a name from the index (examples below).

```text
@github herndoch/pathology-hub-dev

Build the Anki deck for: SERIES

Read and follow:
- docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md
- docs/HANDOFF_<FILE>_ANKI_BUILDER_v0_1.md

Then use that handoff’s “Paste-ready builder brief” as your working contract.

Attachments in this message (or already uploaded):
- Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip
- Pathology_Anki_Contextual_Cloze_SOP.pdf
- WHO_WHO_JSON_PROCESSED_HEME.json
- lecture ZIP(s) listed in the series handoff
- manifest.json, frames.jsonl, segments.jsonl (per lecture)

Workflow I want:
1) Confirm sources + list exact accepted-tag roots you will use.
2) Build a SOURCE SPINE from lecture_index.json + transcript.txt (and frames.jsonl for image/time). Do not stop if chunks_indexable is empty/sparse.
3) Propose a card inventory (entity/topic, teaching point, proposed PrimaryTag, front-image candidate) for my approval BEFORE writing all cards — about 1 short table.
4) After I approve scope, draft fronts (diagnosis bold/visible; one-token clozes), shared backs, images, then QA.

If this is a survey/methods lecture (especially BM Intro): treat approach, pitfalls, adequacy, and comparative morphology as first-class teaching points; use lecture-aligned shared backs when a neat WHO disease entity does not apply (SOP §6 allows this).
```

### Copy-paste SERIES → handoff filename

| Say this | Open this file |
|----------|----------------|
| Aggressive B-Cell | `HANDOFF_AGGRESSIVE_B_CELL_ANKI_BUILDER_v0_1.md` |
| AML | `HANDOFF_AML_ANKI_BUILDER_v0_1.md` |
| BM Failure Syndromes | `HANDOFF_BM_FAILURE_SYNDROMES_ANKI_BUILDER_v0_1.md` |
| **BM Intro** | `HANDOFF_BM_INTRO_ANKI_BUILDER_v0_1.md` |
| BM Systemic Manifestations | `HANDOFF_BM_SYSTEMIC_MANIFESTATIONS_ANKI_BUILDER_v0_1.md` |
| Histiocytic | `HANDOFF_HISTIOCYTIC_ANKI_BUILDER_v0_1.md` |
| Hodgkin NLP | `HANDOFF_HODGKIN_NLP_ANKI_BUILDER_v0_1.md` |
| Hodgkin Overview | `HANDOFF_HODGKIN_OVERVIEW_ANKI_BUILDER_v0_1.md` |
| Hodgkin T/NK-Cell | `HANDOFF_HODGKIN_T_NK_CELL_ANKI_BUILDER_v0_1.md` |
| IA-LPD | `HANDOFF_IA_LPD_ANKI_BUILDER_v0_1.md` |
| IHC for LPD | `HANDOFF_IHC_FOR_LPD_ANKI_BUILDER_v0_1.md` |
| MDS/MPN | `HANDOFF_MDS_MPN_ANKI_BUILDER_v0_1.md` |
| Plasma Cell | `HANDOFF_PLASMA_CELL_ANKI_BUILDER_v0_1.md` |
| PT-LPD | `HANDOFF_PT_LPD_ANKI_BUILDER_v0_1.md` |
| Reactive Lymphoid Hyperplasia | `HANDOFF_REACTIVE_LYMPHOID_HYPERPLASIA_ANKI_BUILDER_v0_1.md` |
| Small B-Cell | `HANDOFF_SMALL_B_CELL_ANKI_BUILDER_v0_1.md` |
| Spleen | `HANDOFF_SPLEEN_ANKI_BUILDER_v0_1.md` |

---

## BM Intro — ready-to-paste (high-yield survey)

Use this instead of the generic second message when starting BM Intro. Zero gated chunks is a **retrieval gate failure**, not empty content (700 ASR segments, 47 frames, ~52 min).

```text
@github herndoch/pathology-hub-dev

Build the Anki deck for: BM Intro (Heme SH Introduction to Bone Marrow Interpretation).

Read and obey:
- docs/HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md
- docs/HANDOFF_BM_INTRO_ANKI_BUILDER_v0_1.md

CRITICAL CONTEXT
- chunks_indexable.jsonl has 0 rows. IGNORE that for scope.
- This talk is HIGH YIELD: BM approach, specimen adequacy, aspirate vs biopsy roles, cellularity, lineage distribution, low-power screening, common pitfalls.
- Do NOT refuse or shrink the deck because gated chunks are empty.
- Scope from: lecture_index.json, transcript.txt, frames.jsonl (47 slides), segments.jsonl.
- Prefer lecturer emphasis over WHO disease laundry lists. WHO is for shared backs only when an entity genuinely appears.
- For methods/approach topics without a disease tag, use a lecture-aligned shared back (SOP §6) and an exact accepted tag only if one exists; otherwise ask me before inventing tags — never invent tag strings.

Attachments: TNK exemplar zip, SOP PDF, WHO_WHO_JSON_PROCESSED_HEME.json, Heme_SH_BM_Intro_package.zip, plus bm_intro manifest.json / frames.jsonl / segments.jsonl.

First output ONLY: a proposed card inventory table
(topic | teaching pearl | candidate PrimaryTag | frame timestamp | why high-yield).
Wait for my approval before writing cards.
```

---

## One-liner after inventory approval

```text
Approved. Proceed per SOP: one-token clozes, diagnosis visible/bold, Tier-1 images via frames.jsonl, byte-identical shared backs per PrimaryTag, two-column tap-to-expand galleries. Emit QA CSV schema from COMMON/SOP and flag any hard-fails.
```

---

## What ChatGPT still cannot do alone

| Need | Who provides it |
|------|-----------------|
| Handoff law / SOP mapping | GitHub (`@github` + docs) |
| Accepted tags + exemplar style | Your TNK zip upload |
| WHO entity text/figures | Your WHO JSON upload |
| Transcript + slides | Your lecture ZIP (+ frames.jsonl) |
| GCS downloads | You (gsutil / Drive), not ChatGPT |

---

## Context hygiene

- Prefer **one series per ChatGPT chat**.
- Keep Cursor agent chats separate from ChatGPT deck builds.
- After PR #18 is merged, a fresh Cursor agent only needs: “see `docs/HANDOFF_HEME_SH_ANKI_BUILDER_INDEX_v0_1.md`”.
