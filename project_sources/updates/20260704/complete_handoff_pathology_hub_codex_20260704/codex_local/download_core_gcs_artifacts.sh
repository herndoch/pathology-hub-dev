#!/usr/bin/env bash
set -euo pipefail
mkdir -p tmp_artifacts/{textbooks,pathout,lectures,who,governance}
gcloud config set project pathology-annotation-project

gcloud storage cp gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl tmp_artifacts/textbooks/
gcloud storage cp gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_manifest.json tmp_artifacts/textbooks/
gcloud storage cp gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_docstore.jsonl tmp_artifacts/pathout/
gcloud storage cp gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_manifest.json tmp_artifacts/pathout/
gcloud storage cp gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl tmp_artifacts/lectures/
gcloud storage cp gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_manifest_STRICT_CYTO_v9.json tmp_artifacts/lectures/
gcloud storage cp 'gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/*.json' tmp_artifacts/who/ || true
gcloud storage cp gs://pathology_hub/06_audits/tags/governance/v10_5/PATHOLOGY_HUB_GOVERNED_CLEANUP_API_PROOF_v10_5_2.json tmp_artifacts/governance/ || true
