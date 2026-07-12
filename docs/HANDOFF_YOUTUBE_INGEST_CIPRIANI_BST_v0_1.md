# YouTube ingest handoff — Cipriani BST board review

Target: https://www.youtube.com/watch?v=NOmOHTh-vtY  
Title: Bone & Soft Tissue Board Review 2026-04-23 (Nicole Cipriani)  
Root: `BST` · Playback: YouTube (`&t=NNNs`)

## Preferred path: Colab first (Heme-style)

Upload and run:

`notebooks/YouTube_Lecture_Ingest_to_Deck_Package_v0_1.ipynb`

Instructions: `docs/COLAB_TODO_YOUTUBE_LECTURE_INGEST.md`

Colab downloads/transcribes/uploads the deck sidecar. Then tell the agent to **gate + vector rebuild**.

## Fallback (cloud agent)

Cloud IPs are bot-blocked. Only use if Colab is unavailable:

- `--cookies cookies.txt`, or
- local `--audio` / `--video` into `scripts/ingest_youtube_lecture_to_deck_package_v0_1.py`

## After sidecar exists

1. Agent: semantic gate v0_2 (`BST` leaves) → upload `chunks_indexable.jsonl`
2. Agent: `build_lecture_vector_from_deck_packages_v0_1.py --upload --promote-live`
3. Operator: Cloud Run env bump `LECTURE_MANIFEST_REFRESH_TS` so pods re-download FAISS

## Gate / URL note

Semantic gate emits YouTube `&t=NNNs` when `video_url` is youtube.com / youtu.be (GCS stays `#t=`).
