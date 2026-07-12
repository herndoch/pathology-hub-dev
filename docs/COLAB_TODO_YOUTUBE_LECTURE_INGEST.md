# Colab: YouTube lecture → deck package (v0.1)

Same split as Heme SH frames: **you run Colab first**, agent gates + rebuilds after the sidecar lands.

**Upload this notebook to Colab:**

`notebooks/YouTube_Lecture_Ingest_to_Deck_Package_v0_1.ipynb`

(File → Upload notebook, or copy to Drive.)

---

## Default video

https://www.youtube.com/watch?v=NOmOHTh-vtY  
Bone & Soft Tissue Board Review 2026-04-23 (Nicole Cipriani) · root `BST` · playback **YouTube** (`&t=NNNs`)

## Colab secrets

| Secret | Used for |
|--------|----------|
| `OPEN_AI_KEY_01` (preferred) or `OPENAI_API_KEY` | Whisper `whisper-1` |

Auth: Colab `auth.authenticate_user()` for GCS write to `pathology_hub` / `pathology-hub-0`.

## What Colab does

1. `yt-dlp` audio (+ optional ≤480p video for frames)
2. Whisper timed segments
3. Optional ffmpeg frame sample
4. Write deck sidecar (`manifest` / `segments` / `frames` / empty `chunks_indexable`)
5. Upload to `gs://pathology_hub/02_normalized/lectures/deck_packages/<package_id>/`
6. Optional slides → `gs://pathology-hub-0/_asset_library/lectures/<stem>/`
7. Audit under `gs://pathology_hub/06_audits/lectures/deck_packages/youtube_colab_ingest_*/`

**Does not:** semantic gate, FAISS rebuild, Cloud Run refresh, claim API exposure.

## After upload

Copy the printed `PACKAGE_ID` into the agent chat (or say **gate Cipriani**). Agent:

```bash
# pull package, gate with BST leaf embeddings, re-upload chunks
python scripts/build_lecture_deck_semantic_indexable_chunks_v0_2.py \
  --package-dir outputs/lecture_deck_packages_v0_1/<package_id> \
  --leaf-dir outputs/bst_browse_leaf_embeddings_v0_1 \
  --root BST

python scripts/build_lecture_vector_from_deck_packages_v0_1.py --upload --promote-live
```

Then your SA refreshes Cloud Run:

```bash
gcloud run services update pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --update-env-vars=LECTURE_MANIFEST_REFRESH_TS=$(date -u +%Y%m%dT%H%M%SZ)
```

## Why Colab (not cloud agent)

YouTube bot-checks block yt-dlp from typical cloud IPs. Colab usually succeeds without cookies. Matches the Heme pattern: media/assets in Colab, indexing work in the agent.
