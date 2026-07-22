# YouTube ingest — Ultra sprint plan (v0.1)

Goal: burn Cursor Ultra on the parts agents can own; keep your time to Colab “Run all + delete runtime.”

## Split of labor

| Who | Job |
|-----|-----|
| **You (Colab)** | One video per deleted runtime via `YouTube_Lecture_Queue_Colab_v0_1.ipynb` |
| **Agent** | Gate empty packages, FAISS rebuild `--promote-live`, Cloud Run lecture refresh |
| **Neither yet** | Broader board-review URL inventory (add rows to queue JSON when you find them) |

## Already done

- Remastered **YT_Skin / YT_GI / YT_Cyto** → in live FAISS
- **Cipriani BST** live YT package → gated + indexed
- **Gardner BST** Colab sidecar → **gated 2026-07-22 (10 chunks)**; FAISS promote next
- **YT_Derm** ignored on purpose

## Your next Colab target

1. Open queue notebook (Open in Colab badge in notebook)
2. `INDEX = 0` → Damron breast (`rCdaaTDesPQ`, root `Breast`)
3. Run all → paste `PACKAGE_ID` here
4. Delete runtime (required)

Queue file: `docs/youtube_ingest_queue_v0_1.json`

## Agent loop after each paste

```bash
# gate one
python scripts/gate_youtube_deck_package_from_gcs_v0_1.py \
  --package-id <PACKAGE_ID> --root Breast \
  --leaf-dir outputs/breast_browse_leaf_embeddings_v0_1

# or scan all live YT pending
python scripts/gate_pending_youtube_deck_packages_v0_1.py \
  --leaf-dir-map BST=outputs/bst_browse_leaf_embeddings_v0_1 \
  --leaf-dir-map Breast=outputs/breast_browse_leaf_embeddings_v0_1

# then (batch, not every video if rushing)
python scripts/build_lecture_vector_from_deck_packages_v0_1.py --upload --promote-live
# bump Cloud Run LECTURE_MANIFEST_REFRESH_TS / new revision
```

## Success for one video

1. Sidecar on GCS under `deck_packages/<id>/`
2. Non-empty `chunks_indexable.jsonl`
3. Rows in live STRICT_CYTO_v9 FAISS with YouTube `&t=` URLs
4. Chat MVP Videos strip returns playable links after refresh

## Out of scope this sprint

- Heme Anki (done)
- Other-specialty Anki
- WSI
- Cookie/CLI ingest on Cursor cloud IPs (bot-blocked)
