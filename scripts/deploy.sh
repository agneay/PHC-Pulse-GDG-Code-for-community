#!/usr/bin/env bash
# Deploy PHC Pulse to Cloud Run (builds the container with Cloud Build).
#
#   GEMINI_API_KEY=... ./scripts/deploy.sh          # Gemini via Google AI Studio key
#   USE_VERTEX=1 ./scripts/deploy.sh                # Gemini via Vertex AI (service account)
#
# Notes
# * The prototype keeps its warehouse in SQLite inside the container, so it runs as a single
#   instance (--max-instances 1). Data is re-seeded on a cold start; set MIN_INSTANCES=1 to keep
#   demo state alive between visits (this keeps one instance billed while idle).
# * Production swaps SQLite for BigQuery/Firestore (see /bigquery) and removes that limit.
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-south1}"           # Mumbai
SERVICE="${SERVICE:-phc-pulse}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"

echo "Deploying $SERVICE to project=$PROJECT region=$REGION"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  --project "$PROJECT"

ENV_VARS="GEMINI_MODEL=${MODEL},PHC_AUTH_SECRET=${PHC_AUTH_SECRET:-$(openssl rand -hex 16)}"
if [[ -n "${PHC_TODAY:-}" ]]; then ENV_VARS="${ENV_VARS},PHC_TODAY=${PHC_TODAY}"; fi

if [[ "${USE_VERTEX:-}" == "1" ]]; then
  gcloud services enable aiplatform.googleapis.com --project "$PROJECT"
  ENV_VARS="${ENV_VARS},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${VERTEX_LOCATION:-us-central1}"
  echo "Grant the Cloud Run service account roles/aiplatform.user if Gemini calls return 403."
elif [[ -n "${GEMINI_API_KEY:-}" ]]; then
  # Store the key in Secret Manager instead of a plain env var.
  gcloud services enable secretmanager.googleapis.com --project "$PROJECT"
  if ! gcloud secrets describe gemini-api-key --project "$PROJECT" >/dev/null 2>&1; then
    printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=- --project "$PROJECT"
  else
    printf '%s' "$GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=- --project "$PROJECT"
  fi
  SECRET_FLAG=(--set-secrets "GEMINI_API_KEY=gemini-api-key:latest")
else
  echo "WARNING: no GEMINI_API_KEY and USE_VERTEX not set - deploying with rule-based fallbacks only."
fi

gcloud run deploy "$SERVICE" --source . --project "$PROJECT" --region "$REGION" \
  --allow-unauthenticated --memory 1Gi --cpu 1 --timeout 120 \
  --max-instances 1 --min-instances "$MIN_INSTANCES" \
  --set-env-vars "$ENV_VARS" ${SECRET_FLAG[@]+"${SECRET_FLAG[@]}"}

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)'
