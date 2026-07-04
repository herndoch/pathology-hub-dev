# Curriculum Map Readiness Audit v0 - Phase 1 GCS Probe Summary

Generated: 2026-07-04

## Scope

Phase 1 ran approved read-only `gcloud storage ls -l` existence/size probes only.

No GCS objects were uploaded, modified, deleted, downloaded, promoted, or deployed. No v11 promotion, Cloud Run deployment, GPT Builder schema update, or Phase 2 script work was performed.

## Commands run

```bash
gcloud storage ls -l --project=pathology-annotation-project "gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json" > audits/curriculum_map_readiness_v0/gcs_probe/v10_5_2_api_proof_ls.stdout.txt 2> audits/curriculum_map_readiness_v0/gcs_probe/v10_5_2_api_proof_ls.stderr.txt
gcloud storage ls -l --project=pathology-annotation-project "gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl" > audits/curriculum_map_readiness_v0/gcs_probe/textbook_docstore_ls.stdout.txt 2> audits/curriculum_map_readiness_v0/gcs_probe/textbook_docstore_ls.stderr.txt
gcloud storage ls -l --project=pathology-annotation-project "gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_docstore.jsonl" > audits/curriculum_map_readiness_v0/gcs_probe/pathout_docstore_ls.stdout.txt 2> audits/curriculum_map_readiness_v0/gcs_probe/pathout_docstore_ls.stderr.txt
gcloud storage ls -l --project=pathology-annotation-project "gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl" > audits/curriculum_map_readiness_v0/gcs_probe/lecture_docstore_ls.stdout.txt 2> audits/curriculum_map_readiness_v0/gcs_probe/lecture_docstore_ls.stderr.txt
gcloud storage ls -l --project=pathology-annotation-project "gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json" > audits/curriculum_map_readiness_v0/gcs_probe/who_processed_json_ls.stdout.txt 2> audits/curriculum_map_readiness_v0/gcs_probe/who_processed_json_ls.stderr.txt
```

## Probe results

| Input | Objects | Bytes | Human size | Status |
| --- | ---: | ---: | --- | --- |
| v10.5.2 API proof JSON | 1 | 10,306 | 10.06 KiB | found |
| Textbook vector docstore | 1 | 230,912,231 | 220.22 MiB | found |
| PathOut AP-diagnostic vector docstore | 1 | 29,416,947 | 28.05 MiB | found |
| Lecture STRICT_CYTO vector docstore | 1 | 109,448,933 | 104.38 MiB | found |
| WHO processed JSON wildcard | 19 | 14,645,721 | 13.97 MiB | found |

All stderr files were empty.

## 500 MB threshold check

No probed object or wildcard total exceeded 500 MB.

The largest single probed object was the textbook vector docstore at 230,912,231 bytes (220.22 MiB).

## Saved outputs

- `audits/curriculum_map_readiness_v0/gcs_probe/v10_5_2_api_proof_ls.stdout.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/v10_5_2_api_proof_ls.stderr.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/textbook_docstore_ls.stdout.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/textbook_docstore_ls.stderr.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/pathout_docstore_ls.stdout.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/pathout_docstore_ls.stderr.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/lecture_docstore_ls.stdout.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/lecture_docstore_ls.stderr.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/who_processed_json_ls.stdout.txt`
- `audits/curriculum_map_readiness_v0/gcs_probe/who_processed_json_ls.stderr.txt`

## Preliminary confidence after Phase 1

Preliminary confidence: moderate for proceeding to design a local sample-mode audit.

Rationale:

- The expected GCS proof/docstore inputs exist at the documented paths.
- Object sizes are compatible with a future sample-first plan and do not trigger the separate >500 MB download approval rule.
- This phase still does not prove curriculum mapping is live, does not inspect record-level tag cleanliness, and does not validate v11.

## Blockers before Phase 2 or sample downloads

- Phase 2 script creation requires explicit approval.
- Any future `gcloud` read/download command requires approval before execution.
- Full downloads or full-mode audit remain out of scope until explicitly approved.
