# Textbook OncoTree (local / shareable) v0_1

Visual OncoTree of **textbook** primary tags (v2.1 controlled), separate from the
Lecture Video OncoTree. Click a leaf for samples; open a sample for a modal with
figure (when available), page image, and **Open page in PDF**.

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
  gs://pathology_hub/02_normalized/source_registry/textbook_page_image_inventory_v1.jsonl \
  /tmp/tb_idx/

python3 scripts/build_textbook_oncotree_index_v0_1.py \
  --catalog /tmp/tb_idx/textbook_primary_tag_catalog_v2_1.jsonl \
  --docstore /tmp/tb_idx/docstore_v2_1.jsonl \
  --webmap /tmp/tb_idx/webmap.jsonl \
  --page-inv /tmp/tb_idx/page_inv.jsonl
```

(Adjust local filenames to match what you downloaded.)

## Notes

- Leaves show capped samples (4 text + 4 figures), not every chunk.
- Page PNG + PDF `#page=` links are joined from page inventory on `(source_id, page)`.
- Generated / review-required tags are omitted.
- Sibling site: `frontend/lecture_video_oncotree_v0_1/` (timestamped videos).
