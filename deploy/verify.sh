#!/usr/bin/env bash
# Comprueba contra GCP real: 403 sin token y 200 con token.
set -euo pipefail
cd "$(dirname "$0")"
source ./env

URL=$(gcloud run services describe "$API_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')

check() {
  local expected=$1 got=$2 label=$3
  if [[ "$got" == "$expected" ]]; then echo "OK   $label -> $got"; else echo "FAIL $label -> $got (esperado $expected)"; exit 1; fi
}

check 403 "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health")" "sin token"

# Con cuenta de usuario: print-identity-token SIN --audiences.
TOKEN=$(gcloud auth print-identity-token)
check 200 "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$URL/whoami")" "con token"
curl -s -H "Authorization: Bearer $TOKEN" "$URL/whoami"; echo
