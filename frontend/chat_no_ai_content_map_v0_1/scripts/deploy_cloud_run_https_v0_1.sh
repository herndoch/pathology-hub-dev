#!/usr/bin/env bash
# Deploy static no-AI content map to Cloud Run + optional domain mapping.
#
# Usage:
#   ./scripts/deploy_cloud_run_https_v0_1.sh
#   MAP_DOMAIN=1 ./scripts/deploy_cloud_run_https_v0_1.sh
#
# Domain: no-ai-chat.pathologynotebook.com (CNAME → ghs.googlehosted.com)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GCP_PROJECT:-pathology-annotation-project}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${CLOUD_RUN_SERVICE:-pathology-hub-no-ai-chat}"
DOMAIN="${CUSTOM_DOMAIN:-no-ai-chat.pathologynotebook.com}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-1}"
MAP_DOMAIN="${MAP_DOMAIN:-0}"

echo "Project:  $PROJECT"
echo "Region:   $REGION"
echo "Service:  $SERVICE"
echo "Domain:   $DOMAIN"
echo "Public:   $ALLOW_UNAUTHENTICATED"
echo "Map DNS:  $MAP_DOMAIN"

if [[ ! -f "$ROOT/data/chat_no_ai_content_map_v0_1.json" ]]; then
  echo "Missing data/chat_no_ai_content_map_v0_1.json — rebuild first." >&2
  exit 1
fi

AUTH_FLAG=(--allow-unauthenticated)
if [[ "$ALLOW_UNAUTHENTICATED" == "0" || "$ALLOW_UNAUTHENTICATED" == "false" ]]; then
  AUTH_FLAG=(--no-allow-unauthenticated)
fi

gcloud config set project "$PROJECT" >/dev/null

gcloud run deploy "$SERVICE" \
  --source="$ROOT" \
  --region="$REGION" \
  --project="$PROJECT" \
  "${AUTH_FLAG[@]}" \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=2 \
  --timeout=60 \
  --cpu-boost \
  --quiet

URL="$(gcloud run services describe "$SERVICE" \
  --region="$REGION" \
  --project="$PROJECT" \
  --format='value(status.url)')"

echo ""
echo "HTTPS URL: $URL"

if [[ "$MAP_DOMAIN" == "1" || "$MAP_DOMAIN" == "true" ]]; then
  if gcloud beta run domain-mappings describe --domain="$DOMAIN" --region="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
    echo "Domain mapping already exists for $DOMAIN"
  else
    gcloud beta run domain-mappings create \
      --service="$SERVICE" \
      --domain="$DOMAIN" \
      --region="$REGION" \
      --project="$PROJECT"
  fi
  echo ""
  echo "DNS (Google Domains / Squarespace): CNAME  no-ai-chat  →  ghs.googlehosted.com."
  gcloud beta run domain-mappings describe --domain="$DOMAIN" --region="$REGION" --project="$PROJECT" \
    --format='yaml(status.resourceRecords,status.conditions)' || true
fi

echo "Done."
