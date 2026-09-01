# Lecture → topics map (shareable) v0_1

**Reverse** content map for education leadership: pick a **lecture**, see its
**topics of interest**, then the **timestamped segments / transcript excerpts**.

Companion to the topic-first OncoTree:
`frontend/lecture_video_oncotree_v0_1/` (topic → clips).

## Off-target / confidence (important)

Source tags are **automated** `semantic_gated_v0_2`. That gate still admits
**off-target** topic hits (wrong entity, low margin vs runner-up).

This package:

- Labels each segment `confidence`: `high` / `medium` / `low`
- **Defaults the UI + leadership CSVs to high-confidence only**
  (`tag_score ≥ 0.65` and `tag_margin ≥ 0.05`)
- Offers a toggle / separate CSV for the full gated set (includes uncertain)

## Share formats

| Format | Path | Notes |
|--------|------|-------|
| Interactive HTML | this folder | default = high-confidence |
| JSON index | `data/lecture_to_topics_index_v0_1.json` | all tiers, with `confidence` |
| CSV lecture summary | `data/exports/lectures_summary_high_confidence_v0_1.csv` | leadership default |
| CSV high-conf segments | `data/exports/lecture_topic_segments_high_confidence_v0_1.csv` | leadership default |
| CSV all gated | `data/exports/lecture_topic_segments_all_gated_v0_1.csv` | includes uncertain |

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

## Notes

- ~137 lectures in source docstore; high-confidence subset is smaller.
- Playback uses public video URLs; user presses play (no autoplay).
