# Lecture Video OncoTree (local / shareable) v0_1

A **video-only** taxonomy browser for Pathology Hub timestamped lecture clips.
Uses the same **visual OncoTree** (SVG links, colored dots, expand/zoom) as Chat
MVP Browse — filtered to tags that already have seekable lecture segments.
Built for mentoring / edu-leadership demos; share as a static folder (no Chat
MVP / Cloud Run required).

## What’s in the box

| Path | Role |
|------|------|
| `index.html` | UI shell |
| `static/app.js` | Tree + clip list + HTML5 player (`#t=` seek) |
| `static/style.css` | Layout |
| `data/video_oncotree_index_v0_1.json` | Built index (roots → tagged leaves → clips) |

Source of truth for clips:

`gs://pathology_hub/03_indexes/lectures/vector_deck_packages_v0_1/lecture_deck_packages_vector_docstore_v0_1.jsonl`

## Run locally

From this directory:

```bash
cd frontend/lecture_video_oncotree_v0_1
python3 -m http.server 8765
```

Open: http://127.0.0.1:8765/

(Use any static server; `file://` may block `fetch` of the JSON.)

## Rebuild the index

```bash
# download docstore once
gcloud storage cp \
  gs://pathology_hub/03_indexes/lectures/vector_deck_packages_v0_1/lecture_deck_packages_vector_docstore_v0_1.jsonl \
  /tmp/lecture_docstore.jsonl

python3 scripts/build_lecture_video_oncotree_index_v0_1.py \
  --docstore /tmp/lecture_docstore.jsonl
```

## Share with leadership

1. Zip the whole `frontend/lecture_video_oncotree_v0_1/` folder, **or**
2. Host the folder on any static HTTPS host / Drive preview with a local server, **or**
3. Later: optional Cloud Storage website bucket / Cloud Run static — not wired yet.

Playback uses public `https://storage.googleapis.com/pathology-hub-0/source_videos/...` URLs
already present on the docstore rows.

## Not claimed

- Not the full Browse OncoTree leaf set (only tags that have gated lecture clips).
- Not human QA of every clip tag.
- Not deployed to `chat.pathologynotebook.com` by this package.
