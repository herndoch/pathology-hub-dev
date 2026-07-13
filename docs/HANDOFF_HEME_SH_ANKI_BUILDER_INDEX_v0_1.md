# Handoff Index — Heme SH Contextual Cloze Anki Builders (v0_1)

Date: 2026-07-13

**Shared rules:** [`HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md`](HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md)  
**ChatGPT paste prompts:** [`HANDOFF_CHATGPT_HEME_ANKI_PROMPTS_v0_1.md`](HANDOFF_CHATGPT_HEME_ANKI_PROMPTS_v0_1.md)

Each series handoff is self-sufficient for attachments/paths and points at COMMON for SOP/QA.

**Survey caveat:** BM Intro has **0** gated chunks but is high-yield — see its handoff + the ChatGPT BM Intro paste block. Gated chunks measure disease-entity retrieval fit, not teaching value.

## Series

| Series | Handoff | Lectures | Segments | Frames | Gated chunks |
|--------|---------|----------|----------|--------|--------------|
| Aggressive B-Cell | `HANDOFF_AGGRESSIVE_B_CELL_ANKI_BUILDER_v0_1.md` | 1 | 877 | 66 | 16 |
| AML | `HANDOFF_AML_ANKI_BUILDER_v0_1.md` | 1 | 443 | 65 | 5 |
| BM Failure Syndromes | `HANDOFF_BM_FAILURE_SYNDROMES_ANKI_BUILDER_v0_1.md` | 1 | 476 | 22 | 9 |
| BM Intro | `HANDOFF_BM_INTRO_ANKI_BUILDER_v0_1.md` | 1 | 700 | 47 | 0 |
| BM Systemic Manifestations | `HANDOFF_BM_SYSTEMIC_MANIFESTATIONS_ANKI_BUILDER_v0_1.md` | 1 | 595 | 92 | 2 |
| Histiocytic | `HANDOFF_HISTIOCYTIC_ANKI_BUILDER_v0_1.md` | 1 | 464 | 38 | 16 |
| Hodgkin NLP (NLPHL) | `HANDOFF_HODGKIN_NLP_ANKI_BUILDER_v0_1.md` | 1 | 360 | 66 | 11 |
| Hodgkin Overview | `HANDOFF_HODGKIN_OVERVIEW_ANKI_BUILDER_v0_1.md` | 1 | 410 | 74 | 6 |
| Hodgkin T/NK-Cell (parts 1–2) | `HANDOFF_HODGKIN_T_NK_CELL_ANKI_BUILDER_v0_1.md` | 2 | 891 | 186 | 16 |
| IA-LPD (Immunodeficiency-Associated LPD) | `HANDOFF_IA_LPD_ANKI_BUILDER_v0_1.md` | 1 | 308 | 39 | 4 |
| IHC for LPD | `HANDOFF_IHC_FOR_LPD_ANKI_BUILDER_v0_1.md` | 1 | 434 | 80 | 3 |
| MDS/MPN (parts 1–3) | `HANDOFF_MDS_MPN_ANKI_BUILDER_v0_1.md` | 3 | 2437 | 169 | 17 |
| Plasma Cell | `HANDOFF_PLASMA_CELL_ANKI_BUILDER_v0_1.md` | 1 | 447 | 34 | 8 |
| PT-LPD (Post-Transplant LPD) | `HANDOFF_PT_LPD_ANKI_BUILDER_v0_1.md` | 1 | 446 | 27 | 16 |
| Reactive Lymphoid Hyperplasia | `HANDOFF_REACTIVE_LYMPHOID_HYPERPLASIA_ANKI_BUILDER_v0_1.md` | 1 | 622 | 72 | 5 |
| Small B-Cell (parts 1–2) | `HANDOFF_SMALL_B_CELL_ANKI_BUILDER_v0_1.md` | 2 | 1804 | 238 | 25 |
| Spleen | `HANDOFF_SPLEEN_ANKI_BUILDER_v0_1.md` | 1 | 650 | 105 | 15 |

## Universal attach / exclude

**Always attach:** TNK exemplar zip, Contextual Cloze SOP PDF, `WHO_WHO_JSON_PROCESSED_HEME.json`, lecture ZIP(s), per-lecture `manifest.json` + `frames.jsonl` + `segments.jsonl`.

**Optional:** `chunks_indexable.jsonl` as navigation only.

**Never attach:** `tag_audit.json`, `chunk_audit.json`, `audit.json`.

**Tag law:** accepted-tag JSON in the TNK exemplar only.

## Scope override (all series)

Teaching grain = transcript + lecture index (+ segments for timestamps).  
Gated chunks are an index, not syllabus coverage.
