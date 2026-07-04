# GCS Paths and Objects

## Buckets

```text
Project: pathology-annotation-project
Artifact bucket: gs://pathology_hub
Legacy/source bucket: gs://pathology-hub-0
Raw textbooks: gs://pathology-hub-0/source_pdfs/
Raw lectures/videos: gs://pathology-hub-0/source_videos/
WHO processed JSON: gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json
```

## Backend-consumed paths affected by v10.5

```text
gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl
gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_manifest.json
gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_docstore.jsonl
gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_manifest.json
gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl
gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_manifest_STRICT_CYTO_v9.json
gs://pathology_hub/02_normalized/textbooks/lean/textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl
```

## Governance staging/audit/backup prefixes

```text
gs://pathology_hub/02_normalized/tags/governance/v10_5/
gs://pathology_hub/06_audits/tags/governance/v10_5/
gs://pathology_hub/99_backups/governance_v10_5/<run_ts>/
```

## v11 target paths if run

```text
gs://pathology_hub/02_normalized/tags/curriculum_hardening/v11/<run_ts>/
gs://pathology_hub/06_audits/tags/curriculum_hardening/v11/<run_ts>/
gs://pathology_hub/99_backups/curriculum_tag_hardening_v11/<run_ts>/
gs://pathology_hub/03_indexes/tags/curriculum_hardening/v11/pathology_hub_approved_curriculum_tag_index_v11.sqlite
```
