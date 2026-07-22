# Colab queue: YouTube lectures → deck packages (v0.1)

**Notebook:** `notebooks/YouTube_Lecture_Queue_Colab_v0_1.ipynb`

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herndoch/pathology-hub-dev/blob/master/notebooks/YouTube_Lecture_Queue_Colab_v0_1.ipynb)

Authoritative queue status: `docs/youtube_ingest_queue_v0_1.json` (Gardner gated 2026-07-22; Damron still pending Colab).

## Why one video per runtime

YouTube bot / age gates stick to a warm Colab IP. Restarting (disconnect **and delete** runtime) between videos is the no-cookies workaround that worked for Cipriani.

## Loop

1. Cell **1a** — fill `QUEUE` once (all URLs)
2. Cell **1b** — set `INDEX` (0, then 1, …)
3. Runtime → **Run all**
4. Paste printed `PACKAGE_ID` to the agent
5. Runtime → **Disconnect and delete runtime**
6. Reconnect → `INDEX += 1` → Run all

## Cell 1a / 1b shape

```python
QUEUE = [
    ("https://www.youtube.com/watch?v=rCdaaTDesPQ", "Breast", None),  # Damron
    ("https://www.youtube.com/watch?v=1WuhaGCtj4k", "BST", None),      # Gardner
]
INDEX = 0  # bump after each deleted runtime
```

## Behavior

- Captions first (timestamps, no Whisper)
- Else audio-only Whisper with recompress + 10-min chunks if >24MB
- `SKIP_FRAMES = True` by default
- Upload sidecar to `gs://pathology_hub/02_normalized/lectures/deck_packages/<package_id>/`
- Does **not** gate or rebuild FAISS (agent)

## Age-restricted

Some Damron videos require sign-in for media. Captions may still work. If both fail after a fresh runtime, skip that URL or use cookies (out of scope for this notebook).

## Secret

`OPEN_AI_KEY_01` — only required when Whisper runs.

## Age-restricted (Damron)

YouTube age gate blocks **media** in Colab without cookies. The queue notebook defaults to `CAPTIONS_ONLY = True`:

1. Fresh runtime (delete previous)
2. Keep `CAPTIONS_ONLY = True` and `PREFER_CAPTIONS = True`
3. Run all — if captions work, you still get a deck package (no Whisper)
4. If captions also fail → **skip Damron** for now; add another non-age-restricted URL to `QUEUE`

Cookie-based yt-dlp is possible later but is a separate path (not the Ultra no-cookies loop).

