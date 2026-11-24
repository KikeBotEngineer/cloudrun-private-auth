#!/usr/bin/env bash
# Despliega el gateway público con API key y le da run.invoker sobre la API privada.
#
# Requisito: el secreto $API_KEYS_SECRET con el valor "consumidor:sha256,...". Crearlo con:
#   printf 'testers:<sha256>' | gcloud secrets create gateway-api-keys --data-file=-
set -euo pipefail
cd "$(dirname "$0")"
source ./env

SA_EMAIL="$GATEWAY_SA@$PROJECT_ID.iam.gserviceaccount.com"
API_URL=$(gcloud run services describe "$API_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')

gcloud secrets describe "$API_KEYS_SECRET" --project "$PROJECT_ID" >/dev/null \
  || { echo "Falta el secreto $API_KEYS_SECRET (ver cabecera del script)"; exit 1; }

gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$GATEWAY_SA" --project "$PROJECT_ID" --display-name "API key gateway"

gcloud secrets add-iam-policy-binding "$API_KEYS_SECRET" --project "$PROJECT_ID" \
  --member "serviceAccount:$SA_EMAIL" --role roles/secretmanager.secretAccessor >/dev/null

gcloud run services add-iam-policy-binding "$API_SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --member "serviceAccount:$SA_EMAIL" --role roles/run.invoker >/dev/null

# El Dockerfile usa la raíz del repo como contexto; se arma un contexto mínimo.
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/gateway" "$STAGE/client"
cp ../gateway/Dockerfile "$STAGE/Dockerfile"
cp -r ../gateway/app ../gateway/requirements.txt "$STAGE/gateway/"
cp ../client/identity_token.py "$STAGE/client/"

# ALLOWED_ROUTES lleva comas y espacios: se usa '@' como delimitador de --set-env-vars.
gcloud run deploy "$GATEWAY_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --source "$STAGE" \
  --service-account "$SA_EMAIL" \
  --allow-unauthenticated \
  --max-instances "${GATEWAY_MAX_INSTANCES:-3}" \
  --set-env-vars "^@^UPSTREAM_URL=$API_URL@ALLOWED_ROUTES=$ALLOWED_ROUTES@UPSTREAM_TIMEOUT_SECONDS=$UPSTREAM_TIMEOUT_SECONDS" \
  --set-secrets "API_KEYS=$API_KEYS_SECRET:latest"

echo "Gateway: $(gcloud run services describe "$GATEWAY_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')"
