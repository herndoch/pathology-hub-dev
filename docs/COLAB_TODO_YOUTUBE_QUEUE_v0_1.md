# Colab queue: YouTube lectures → deck packages (v0.1)

**Notebook:** `notebooks/YouTube_Lecture_Queue_Colab_v0_1.ipynb`

## Why one video per runtime

YouTube bot / age gates stick to a warm Colab IP. Restarting (disconnect **and delete** runtime) between videos is the no-cookies workaround that worked for Cipriani.

## Loop

1. Edit **Cell 1 only** — set `INDEX` and fill `QUEUE`
2. Runtime → **Run all**
3. Paste printed `PACKAGE_ID` to the agent
4. Runtime → **Disconnect and delete runtime**
5. `INDEX += 1` → reconnect → Run all

## Cell 1 shape

```python
INDEX = 0
QUEUE = [
    ("https://www.youtube.com/watch?v=rCdaaTDesPQ", "Breast", None),
    ("https://www.youtube.com/watch?v=1WuhaGCtj4k", "BST", None),
]
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
