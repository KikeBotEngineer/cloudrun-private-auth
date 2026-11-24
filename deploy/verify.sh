#!/usr/bin/env bash
# Comprueba contra GCP real:
#   API privada: 403 sin token, 200 con token.
#   Gateway (si está desplegado): 401 sin key; con GATEWAY_API_KEY, 200 y que llega con su SA.
# Uso: GATEWAY_API_KEY=<key> ./deploy/verify.sh   (la key nunca va en deploy/env)
set -euo pipefail
cd "$(dirname "$0")"
source ./env

url_of() { gcloud run services describe "$1" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)'; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
check() {
  local expected=$1 got=$2 label=$3
  if [[ "$got" == "$expected" ]]; then echo "OK   $label -> $got"; else echo "FAIL $label -> $got (esperado $expected)"; exit 1; fi
}

URL=$(url_of "$API_SERVICE")
check 403 "$(code "$URL/health")" "API sin token"

# Usuario: print-identity-token SIN --audiences (con usuario falla). Service account: con --audiences.
if [[ "$(gcloud config get-value account 2>/dev/null)" == *.gserviceaccount.com ]]; then
  TOKEN=$(gcloud auth print-identity-token --audiences "$URL")
else
  TOKEN=$(gcloud auth print-identity-token)
fi
check 200 "$(code -H "Authorization: Bearer $TOKEN" "$URL/whoami")" "API con token"
curl -s -H "Authorization: Bearer $TOKEN" "$URL/whoami"; echo

if ! GW=$(url_of "$GATEWAY_SERVICE" 2>/dev/null); then
  echo "SKIP gateway: $GATEWAY_SERVICE no está desplegado"
  exit 0
fi
check 401 "$(code "$GW/whoami")" "gateway sin key"

if [[ -z "${GATEWAY_API_KEY:-}" ]]; then
  echo "SKIP gateway con key: define GATEWAY_API_KEY para probarlo"
  exit 0
fi
BODY=$(curl -s -w '\n%{http_code}' -H "X-API-Key: $GATEWAY_API_KEY" "$GW/whoami")
check 200 "${BODY##*$'\n'}" "gateway con key"
# La API debe ver la SA del gateway, no al cliente: prueba que el gateway pone su propio token.
EMAIL="$GATEWAY_SA@$PROJECT_ID.iam.gserviceaccount.com"
[[ "$BODY" == *"\"email\":\"$EMAIL\""* ]] && echo "OK   la API ve a $EMAIL" \
  || { echo "FAIL la API no vio a $EMAIL: ${BODY%$'\n'*}"; exit 1; }
