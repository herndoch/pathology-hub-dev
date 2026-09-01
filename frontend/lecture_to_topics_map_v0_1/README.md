# Lecture → topics map (shareable) v0_1

**Reverse** content map for education leadership: pick a **lecture**, see its
**topics of interest**, then the **timestamped segments / transcript excerpts**.

Companion to the topic-first OncoTree:
`frontend/lecture_video_oncotree_v0_1/` (topic → clips).

## Share formats

| Format | Path |
|--------|------|
| Interactive HTML | this folder (`index.html`) |
| JSON index | `data/lecture_to_topics_index_v0_1.json` |
| CSV lecture summary | `data/exports/lectures_summary_v0_1.csv` |
| CSV segment inventory | `data/exports/lecture_topic_segments_v0_1.csv` |

Zip the folder, host statically, or hand leadership the CSVs for spreadsheets.

## Run locally

```bash
cd frontend/lecture_to_topics_map_v0_1
python3 -m http.server 8768
# http://127.0.0.1:8768/
```

## Rebuild

```bash
gcloud storage cp \
  gs://pathology_hub/03_indexes/lectures/vector_deck_packages_v0_1/lecture_deck_packages_vector_docstore_v0_1.jsonl \
  /tmp/lecture_docstore.jsonl

python3 scripts/build_lecture_to_topics_map_v0_1.py \
  --docstore /tmp/lecture_docstore.jsonl
```

Force-add data if gitignored:

```bash
git add -f frontend/lecture_to_topics_map_v0_1/data/
```

## Notes

- Source: gated lecture deck vector docstore (~137 lectures / ~915 segments).
- Only tagged, seekable segments are included.
- Playback uses public `pathology-hub-0` video URLs; user presses play (no autoplay).
