#!/usr/bin/env bash
set -euo pipefail

echo "Project:"
gcloud config get-value project

echo
echo "New canonical bucket:"
gcloud storage ls gs://pathology_hub | head

echo
echo "Legacy/source bucket:"
gcloud storage ls gs://pathology-hub-0 | head

echo
echo "ADC file:"
ls -lh ~/.config/gcloud/application_default_credentials.json

echo
echo "Codex:"
codex --version
