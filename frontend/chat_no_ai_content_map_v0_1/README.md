# Chat content map (no AI) v0_1

Static OncoTree inventory of **source cards and figures** used by Chat MVP
topic prebuilds. No live retrieval and no `answer_markdown` AI synthesis.

Intended public path (not claimed live by this package):
`pathologynotebook.com/chat-no-ai`

## Run locally

```bash
cd frontend/chat_no_ai_content_map_v0_1
python3 -m http.server 8767
# http://127.0.0.1:8767/
```

## Rebuild

```bash
mkdir -p /tmp/prebuilds_all
gcloud storage cp -r \
  gs://pathology_hub/api_exposed/chat_mvp_topic_prebuilds_v0_1/pages \
  /tmp/prebuilds_all/

python3 scripts/build_chat_no_ai_content_map_v0_1.py \
  --pages-dir /tmp/prebuilds_all/pages
```

Force-add the generated JSON if `data/` is gitignored:

```bash
git add -f frontend/chat_no_ai_content_map_v0_1/data/chat_no_ai_content_map_v0_1.json
```

## Notes

- Built from `topic_page_prebuild_v0_1` page JSON only.
- All `Cyto_*` prebuild roots are nested under one **Cytopathology** root
  (`Cyto_Adrenal` → `Cytopathology::Adrenal`, etc.).
- Leaves show capped samples (6 cards + 4 figures).
- Modal opens figure / page image when URLs exist, plus PDF or source link.
- Separate from live Chat MVP at `chat.pathologynotebook.com`.
