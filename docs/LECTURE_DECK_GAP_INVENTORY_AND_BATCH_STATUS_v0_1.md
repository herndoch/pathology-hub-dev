# Gap inventory + batch status (Derm skipped)

Date: 2026-07-12

## T/NK lecture packages (already done — Heme SH)

Local + GCS under `02_normalized/lectures/deck_packages/`:

| Package | Files | Gated chunks |
|---------|-------|-------------:|
| `heme_sh_hodgkin_t_nk_cell_1_v0_1` | manifest, segments.jsonl (482), frames.jsonl (95), chunks_indexable.jsonl, audits | **8** |
| `heme_sh_hodgkin_t_nk_cell_2_v0_1` | same shape; segments 409, frames 91 | **8** |

Index grain: `chunks_indexable.jsonl` only. Video: `Heme_SH_Hodgkin_T_NK_Cell_{1,2}.mp4` joined.

---

## Gaps (cannot convert without content_library JSON)

### GU_Lecture — 4/17 missing content
| Stem | MP4 | Assets/JPGs | Content JSON |
|------|:---:|:-----------:|:------------:|
| GU_Lecture_0_BladderTumors | ✅ | ✅ 57 | ❌ |
| GU_Lecture_0_Papillary_Urothelial_CA | ✅ | ✅ 128 | ❌ |
| GU_Lecture_0_ProstateGrading | ✅ | ✅ 127 | ❌ |
| GU_Lecture_0_ProstateIntraductal | ✅ | ✅ 114 | ❌ |
| GU_Lecture_1–13 (kidney/testis/bladder/prostate) | ✅ | ✅ | ✅ **processed 13** |

### HN_Lecture — 1/9 missing content
| Stem | Gap |
|------|-----|
| HN_Lecture_4_Thyroid2 | MP4+226 JPGs present; **no content JSON** |
| HN_Lecture_3_Thyroid1 | processed but **0 gated chunks** (thyroid entities live mostly under Endo::, not HN::) |

### Thoracic_Lecture — 9/10 missing content
Only `Thoracic_Lecture_1_Lung_Non_Neoplastic1` has content JSON → processed.  
Missing content (MP4+assets exist): Cardiac_Gross, Lung_Gross, Non_Neoplastic2, ARS, ILD, Neoplastic, Molecular1/2, Thymus.

### Derm — skipped (per request)
38 MP4 / 31 asset dirs / 28 content — not processed.

### Other families with large gaps (not in this batch)
| Family | MP4 | Content | Notes |
|--------|----:|--------:|-------|
| Other_Heme | 18 | 1 | almost no content JSON |
| Other_Skin | 20 | 1 | almost no content JSON |
| ASC_Global | 5 | 0 | no content |
| YT_BST / YT_HN / YT_Micro | varies | 0 | no content |
| YT_Derm | — | — | **ignored** (do not process) |
| YT_Skin | 21 | 21 | **remastered** 2026-07-12 → 179 gated Skin chunks |

### Already known asset gap
BST SoftTissue/Bone: asset dirs lack JPGs (ENHANCED JSON only).

---

## Processed this turn (skip Derm)

| Family | Converted | Gated chunks |
|--------|----------:|-------------:|
| GU_Lecture | 13 | **96** |
| HN_Lecture | 8 | **24** |
| Thoracic_Lecture | 1 | **14** |
| YT_GI | 16 | **36** |
| YT_Cyto | 17 | **85** |

Sidecars: `gs://pathology_hub/02_normalized/lectures/deck_packages/{gu,hn,thoracic,yt_gi,yt_cyto}_*_v0_1/`  
Not FAISS/API exposed yet.
