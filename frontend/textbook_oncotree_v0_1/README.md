# Textbook OncoTree (local / shareable) v0_1

Visual OncoTree of **textbook** primary tags (v2.1 controlled), separate from the
Lecture Video OncoTree. Click a leaf to browse sample page excerpts and figures.

## Run locally

```bash
cd frontend/textbook_oncotree_v0_1
python3 -m http.server 8766
# http://127.0.0.1:8766/
```

Use a different port if the lecture map is already on 8765.

## Rebuild

```bash
gcloud storage cp \
  gs://pathology_hub/02_normalized/textbooks/lean/tags/tag_consolidation_v2_1/textbook_primary_tag_catalog_v2_1.jsonl \
  gs://pathology_hub/03_indexes/textbooks/vector_v2_1_tag_consolidation/textbook_lean_vector_docstore_v2_1.jsonl \
  gs://pathology_hub/02_normalized/textbooks/lean/textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl \
  /tmp/tb_idx/

python3 scripts/build_textbook_oncotree_index_v0_1.py \
  --catalog /tmp/tb_idx/textbook_primary_tag_catalog_v2_1.jsonl \
  --docstore /tmp/tb_idx/textbook_lean_vector_docstore_v2_1.jsonl \
  --webmap /tmp/tb_idx/textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl
```

## Notes

- Leaves show capped samples (4 text + 4 figures), not every chunk.
- Generated / review-required tags are omitted.
- Sibling site: `frontend/lecture_video_oncotree_v0_1/` (timestamped videos).
