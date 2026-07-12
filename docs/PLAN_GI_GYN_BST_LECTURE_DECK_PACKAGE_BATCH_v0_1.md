# Plan / status — GI, GYN, BST content_library deck packages

Date: 2026-07-12  
Status: **convert + leaf embeddings + semantic gated chunks done** (Derm skipped per request). Vector rebuild still gated.

## Scope

| Family | Stems | Root leaves | Convert | MP4 join | Gated chunks |
|--------|------:|------------:|:-------:|:--------:|-------------:|
| GI_Lecture | 13 | 352 | 13/13 | 13/13 | **78** (13/13 pkgs) |
| Gyn_Lecture | 12 | 502 | 12/12 | 12/12 | **50** (11/12; Grossing1 empty) |
| BST_Lecture | 6 | 431 | 6/6 | 6/6 | **37** (6/6) |
| Derm | — | — | skipped | — | — |

## Audits (GCS)

Convert:
- `gs://pathology_hub/06_audits/lectures/deck_packages/content_library_batch_20260712T132604Z/audit.json` (GI)
- `gs://pathology_hub/06_audits/lectures/deck_packages/content_library_batch_20260712T132700Z/audit.json` (Gyn)
- `gs://pathology_hub/06_audits/lectures/deck_packages/content_library_batch_20260712T132726Z/audit.json` (BST)

Leaf embeddings:
- `gs://pathology_hub/06_audits/lectures/deck_packages/gi_browse_leaf_embeddings_v0_1/`
- `gs://pathology_hub/06_audits/lectures/deck_packages/gyn_browse_leaf_embeddings_v0_1/`
- `gs://pathology_hub/06_audits/lectures/deck_packages/bst_browse_leaf_embeddings_v0_1/`

Gate batches under `gs://pathology_hub/06_audits/lectures/deck_packages/semantic_gated_v0_2_*` (see local `audits/lecture_deck_semantic_gated_v0_2/`).

## Known limitations

1. **BST slides mostly missing** in `_asset_library/lectures/BST_Lecture_*` — SoftTissue/Bone dirs contain only `final_ENHANCED_data.json`, not JPGs. Grossing has slides. Transcript/MP4 sidecars still valid; frame `asset_object_present=false` audited.
2. **GI liver** lectures retain few chunks — many windows fail similarity/margin against sparse liver leaf set (inflammatory/medical liver poorly covered vs neoplastic leaves).
3. **Gyn Grossing1** empty by usefulness gates (procedural).
4. Sidecars only — **not** FAISS/API/Videos-strip exposed until rebuild + audit.
5. Source stem typo preserved: `BST_Lecture_3_SofTissue2` → package `bst_lecture_3_softissue2_v0_1`.

## Principles

Same as Heme/Breast: sidecar under `02_normalized/lectures/deck_packages/<id>/`; index only `chunks_indexable.jsonl`; do not overwrite legacy normalized lecture JSONL.
