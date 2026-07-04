# Curriculum Map v0.2

Generated: 2026-07-04T21:09:10+00:00

This is a local Curriculum Map build for Evidence/Lesson/Research RAG. It is not live, not uploaded, and not deployed.

## Outputs

- `curriculum_records_v0_2.jsonl`
- `curriculum_nodes_v0_2.csv`
- `review_queue_v0_2.csv`
- `rejected_tags_v0_2.csv`
- `curriculum_tag_index_v0_2.sqlite`
- `curriculum_browser_v0_2.html`
- `acceptance_summary_v0_2.json`

## Acceptance

- Build status: `passed_local_visibility_gate`
- Total records processed: 177822
- Visible curriculum records: 137293
- Review queue count: 4245
- Rejected/hidden count: 36284
- Forbidden visible tag count: 0

## Safety

- No GCS upload or mutation.
- No Cloud Run deploy.
- No GPT Builder schema update.
- No v11 promotion.
- Forbidden patterns are never exposed as curriculum nodes.

## Browser (`curriculum_browser_v0_2.html`)

Open locally in any browser (single self-contained HTML file, no server required).

**Summary panel** — build status, visible record count (137,293), review queue (4,245), rejected/hidden (36,284), and forbidden visible tags (must stay 0).

**Curriculum nodes tab** — searchable, filterable list of 6,105 visible curriculum nodes with root dropdown and quick-filter chips for high-volume roots (Skin, HN, BST, GI, etc.).

**High-yield sections tab** — representative ABPath tags for major organ systems (Ovary, Prostate, Breast, GI, Lung, Derm, Bone, Soft tissue, Cyto) with root and source filters.

Review queue and rejected counts are shown for transparency; those tags are intentionally excluded from the node tables. See `review_queue_v0_2.csv` and `rejected_tags_v0_2.csv` for full lists.
