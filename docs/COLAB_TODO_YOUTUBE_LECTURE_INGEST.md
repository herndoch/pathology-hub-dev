# Colab: YouTube lecture → deck package (v0.1)

**Notebook:** `notebooks/YouTube_Lecture_Ingest_to_Deck_Package_v0_1.ipynb`

## Current target

https://www.youtube.com/watch?v=rCdaaTDesPQ  
Anatomic Pathology Board Review: Breast Pathology (Damron) · root `Breast` · playback YouTube `&t=`

## No-cookies recipe

1. If bot-blocked: **Runtime → Disconnect and delete runtime → Connect**
2. Prefer captions (`PREFER_CAPTIONS = True`)
3. Else audio-only Whisper — notebook **recompresses** then **10-min chunks** if still >24MB (fixes the 25MB API limit)
4. `SKIP_FRAMES = True`

```python
YOUTUBE_URL = "https://www.youtube.com/watch?v=rCdaaTDesPQ"
ROOT = "Breast"
SKIP_FRAMES = True
PREFER_CAPTIONS = True
```

Secret: `OPEN_AI_KEY_01` (only needed if Whisper runs).

Paste printed `PACKAGE_ID` back to the agent for gate + vector rebuild.
