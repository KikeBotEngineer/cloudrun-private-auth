#!/usr/bin/env bash
# Workload Identity Federation para GitHub Actions: sin llaves JSON.
# Crea el pool, el provider (restringido a $GITHUB_REPO en main), la SA de CI y su run.invoker.
# Requiere `gh` autenticado para leer el ID numérico del repo.
set -euo pipefail
cd "$(dirname "$0")"
source ./env

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format 'value(projectNumber)')
SA_EMAIL="$CI_SA@$PROJECT_ID.iam.gserviceaccount.com"
POOL_ID="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL"

gcloud iam workload-identity-pools describe "$WIF_POOL" --project "$PROJECT_ID" --location global >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools create "$WIF_POOL" --project "$PROJECT_ID" --location global \
       --display-name "GitHub Actions"

# Se usa el ID numérico del repo, no su nombre: si el repo se renombra o borra,
# otro que registre el mismo nombre no cumple la condición.
REPO_ID=$(gh api "repos/$GITHUB_REPO" --jq .id)

# Solo workflows de este repo corriendo sobre main (una rama cualquiera no obtiene la SA).
PROVIDER_ARGS=(
  --project "$PROJECT_ID" --location global --workload-identity-pool "$WIF_POOL"
  --issuer-uri "https://token.actions.githubusercontent.com"
  --attribute-mapping "google.subject=assertion.sub,attribute.repository_id=assertion.repository_id"
  --attribute-condition "assertion.repository_id == '$REPO_ID' && assertion.ref == 'refs/heads/main'"
)
# create o update: re-ejecutar el script aplica siempre la condición actual.
if gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER" --project "$PROJECT_ID" \
     --location global --workload-identity-pool "$WIF_POOL" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers update-oidc "$WIF_PROVIDER" "${PROVIDER_ARGS[@]}"
else
  gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" "${PROVIDER_ARGS[@]}"
fi

gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$CI_SA" --project "$PROJECT_ID" --display-name "GitHub Actions CI"

# Solo los workflows de este repo pueden actuar como la SA.
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/$POOL_ID/attribute.repository_id/$REPO_ID" >/dev/null

gcloud run services add-iam-policy-binding "$API_SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --member "serviceAccount:$SA_EMAIL" --role roles/run.invoker >/dev/null

API_URL=$(gcloud run services describe "$API_SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')

cat <<EOF

Configura estas variables del repo en GitHub (Settings > Secrets and variables > Actions > Variables):
  WIF_PROVIDER = $POOL_ID/providers/$WIF_PROVIDER
  CI_SA_EMAIL  = $SA_EMAIL
  API_URL      = $API_URL
EOF
