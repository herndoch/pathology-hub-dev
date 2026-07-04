#!/usr/bin/env bash
set -euo pipefail
gcloud config set project pathology-annotation-project
for p in \
  'gs://pathology_hub/**histopathology**' \
  'gs://pathology_hub/**Histopathology**' \
  'gs://pathology-hub-0/**histopathology**' \
  'gs://pathology-hub-0/**Histopathology**'; do
  echo "### $p"
  gcloud storage ls -r "$p" | head -200 || true
done
