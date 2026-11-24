#!/usr/bin/env bash
# Despliega sample-api en Cloud Run SIN acceso público: solo roles/run.invoker.
set -euo pipefail
cd "$(dirname "$0")"
source ./env

# La cuenta activa de gcloud puede ser un usuario o una service account.
ACCOUNT=$(gcloud config get-value account 2>/dev/null)
[[ -n "$ACCOUNT" ]] || { echo "No hay cuenta activa en gcloud (gcloud auth login)"; exit 1; }
if [[ "$ACCOUNT" == *.gserviceaccount.com ]]; then MEMBER="serviceAccount:$ACCOUNT"; else MEMBER="user:$ACCOUNT"; fi

gcloud run deploy "$API_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --source ../sample-api \
  --no-allow-unauthenticated

# Permite a la cuenta actual invocarla (los owners ya lo tienen).
gcloud run services add-iam-policy-binding "$API_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --member "$MEMBER" \
  --role roles/run.invoker >/dev/null

echo "URL: $(gcloud run services describe "$API_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')"
