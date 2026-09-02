#!/usr/bin/env bash
# Deploy navigable Lecture map HTML to Cloud Run (min instances 0).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GCP_PROJECT:-pathology-annotation-project}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${CLOUD_RUN_SERVICE:-pathology-hub-lecture-map}"
DOMAIN="${CUSTOM_DOMAIN:-lecture-map.pathologynotebook.com}"
MAP_DOMAIN="${MAP_DOMAIN:-0}"

gcloud config set project "$PROJECT" >/dev/null

gcloud run deploy "$SERVICE" \
  --source="$ROOT" \
  --region="$REGION" \
  --project="$PROJECT" \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=60 \
  --cpu-boost \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT" --format='value(status.url)')"
echo "HTTPS URL: $URL"

if [[ "$MAP_DOMAIN" == "1" || "$MAP_DOMAIN" == "true" ]]; then
  if ! gcloud beta run domain-mappings describe --domain="$DOMAIN" --region="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
    gcloud beta run domain-mappings create \
      --service="$SERVICE" \
      --domain="$DOMAIN" \
      --region="$REGION" \
      --project="$PROJECT"
  fi
  echo "DNS: CNAME lecture-map → ghs.googlehosted.com."
fi
