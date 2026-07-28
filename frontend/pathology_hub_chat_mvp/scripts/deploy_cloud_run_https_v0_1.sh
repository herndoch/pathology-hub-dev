#!/usr/bin/env bash
# Deploy Pathology Hub Chat MVP to Cloud Run (Google-managed HTTPS).
#
# Usage:
#   ./scripts/deploy_cloud_run_https_v0_1.sh
#   ALLOW_UNAUTHENTICATED=0 ./scripts/deploy_cloud_run_https_v0_1.sh   # private
#
# Requires: gcloud auth, project pathology-annotation-project, Secret Manager
# secrets OPENAI + PATHOLOGY_HUB_API_KEY accessible to the Cloud Run SA.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GCP_PROJECT:-pathology-annotation-project}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${CLOUD_RUN_SERVICE:-pathology-hub-chat-mvp}"
API_URL="${PATHOLOGY_HUB_API_URL:-https://pathology-hub-v04-vorn5q2kga-uc.a.run.app}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-1}"

echo "Project:  $PROJECT"
echo "Region:   $REGION"
echo "Service:  $SERVICE"
echo "API URL:  $API_URL"
echo "Public:   $ALLOW_UNAUTHENTICATED"

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
  --memory=1Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300 \
  --set-env-vars="PATHOLOGY_HUB_API_URL=${API_URL},OPENAI_MODEL=${OPENAI_MODEL:-gpt-4o}" \
  --set-secrets="OPENAI_API_KEY=OPENAI:latest,PATHOLOGY_HUB_API_KEY=PATHOLOGY_HUB_API_KEY:latest,ELSEVIER_API_KEY=Elsevier:latest,NCBI_API_KEY=NCBI:latest,ONCOKB_API_TOKEN=OncoKB:latest"

URL="$(gcloud run services describe "$SERVICE" \
  --region="$REGION" \
  --project="$PROJECT" \
  --format='value(status.url)')"

echo ""
echo "HTTPS URL: $URL"
echo "Health:    ${URL}/api/health"
echo "Done."
