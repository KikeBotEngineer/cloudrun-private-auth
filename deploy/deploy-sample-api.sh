#!/usr/bin/env bash
# Despliega sample-api en Cloud Run SIN acceso público: solo roles/run.invoker.
set -euo pipefail
cd "$(dirname "$0")"
source ./env

gcloud run deploy "$API_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --source ../sample-api \
  --no-allow-unauthenticated

# Permite al usuario actual invocarla (los owners ya lo tienen).
gcloud run services add-iam-policy-binding "$API_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --member "user:$(gcloud config get-value account)" \
  --role roles/run.invoker >/dev/null

echo "URL: $(gcloud run services describe "$API_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')"
