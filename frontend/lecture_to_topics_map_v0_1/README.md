# Lecture map — navigable HTML for education leadership

Visual **tree** (specialty → lecture → topics) plus clip list / video seek.
Default: **high-confidence** tags only.

## Share with non-tech education folks (recommended)

**Best:** send them a link (no install):

After deploy, use the Cloud Run URL (or custom domain once DNS is set):

```bash
cd frontend/lecture_to_topics_map_v0_1
MAP_DOMAIN=1 ./scripts/deploy_cloud_run_https_v0_1.sh
```

- Service: `pathology-hub-lecture-map` (min instances **0** — idle ≈ $0)
- Optional DNS: `lecture-map` CNAME → `ghs.googlehosted.com.`

**Also fine:** zip this whole folder and have IT host it on any static HTTPS page.

CSVs remain under **Advanced** for spreadsheet users — not the primary handoff.

## Local preview

```bash
cd frontend/lecture_to_topics_map_v0_1
python3 -m http.server 8768
```

## Rebuild data

```bash
python3 scripts/build_lecture_to_topics_map_v0_1.py \
  --docstore /path/to/lecture_deck_packages_vector_docstore_v0_1.jsonl
```
