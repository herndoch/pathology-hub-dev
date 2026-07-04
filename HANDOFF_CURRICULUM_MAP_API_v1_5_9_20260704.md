# Handoff — Curriculum Map API v1.5.9

Date: 2026-07-04

Workstream: Backend API / Custom GPT frontend integration / Curriculum Map v0.2

## Current State

Curriculum Map v0.2 is staged in GCS:

```text
gs://pathology_hub/05_html/curriculum_map/v0_2/
gs://pathology_hub/02_normalized/curriculum_map/v0_2/
gs://pathology_hub/06_audits/curriculum_map/v0_2/
```

Acceptance:

```text
build_status: passed_local_visibility_gate
visible_curriculum_records: 137293
review_queue_count: 4245
rejected_hidden_count: 36284
forbidden_visible_tag_count: 0
```

## Backend Change

Recovered the current Cloud Run source from Cloud Build:

```text
gs://pathology-annotation-project_cloudbuild/source/1782705823.737873-c38a280729284befaf8567bc1168e112.tgz
```

Created deployable backend source:

```text
backend/pathology_hub_v04_curriculum/
```

The implementation adds `sources=["curriculum"]` to the existing `POST /evidence/search` route. No new GPT Action is added.

## Runtime Artifacts

The API loads:

```text
gs://pathology_hub/02_normalized/curriculum_map/v0_2/curriculum_tag_index_v0_2.sqlite
gs://pathology_hub/02_normalized/curriculum_map/v0_2/curriculum_nodes_v0_2.csv
gs://pathology_hub/02_normalized/curriculum_map/v0_2/review_queue_v0_2.csv
gs://pathology_hub/02_normalized/curriculum_map/v0_2/rejected_tags_v0_2.csv
gs://pathology_hub/06_audits/curriculum_map/v0_2/acceptance_summary_v0_2.json
```

The 935 MB uncompressed JSONL is not loaded at startup.

## Stop Point

After staging deploy and smoke tests, stop. Production promotion target is:

```text
pathology-hub-v04
version: 1.5.9-curriculum-map-v02
```

Do not update GPT Builder until staging results are reviewed.
