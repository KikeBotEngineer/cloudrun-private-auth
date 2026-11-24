"""ID tokens para llamar servicios privados de Cloud Run, en cualquier entorno.

Orden de resolución de la credencial:
  1. GCP_ID_TOKEN: token ya emitido (`gcloud auth print-identity-token`). No se refresca.
  2. GOOGLE_APPLICATION_CREDENTIALS: llave JSON de una service account. Se refresca.
  3. Nada: metadata server (Cloud Run, GCE, Functions). Se refresca.

Uso:
    session = get_session("https://sample-api-xxxx.run.app")
    session.get("https://sample-api-xxxx.run.app/whoami").json()
"""

import os
from urllib.parse import urlsplit

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token, service_account
from google.oauth2.credentials import Credentials as StaticCredentials


def normalize_audience(url: str) -> str:
    """Reduce la URL a `https://host`, que es el audience que Cloud Run espera.

    Se arma con hostname (y puerto si no es 443), nunca con netloc: así un
    `usuario:clave@` en la URL no acaba dentro del token ni en un mensaje de error.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(
            "El audience debe ser una URL https:// del servicio "
            f"(esquema {parts.scheme!r}, host {parts.hostname!r})"
        )
    port = f":{parts.port}" if parts.port not in (None, 443) else ""
    return f"https://{parts.hostname}{port}"


def _credentials(audience: str):
    token = os.environ.get("GCP_ID_TOKEN")
    if token:
        return StaticCredentials(token=token)
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_file:
        return service_account.IDTokenCredentials.from_service_account_file(
            key_file, target_audience=audience
        )
    return id_token.fetch_id_token_credentials(audience, request=Request())


def get_token(url: str) -> str:
    """Devuelve un ID token (nunca un access token) con aud = URL base del servicio."""
    creds = _credentials(normalize_audience(url))
    if not creds.valid:
        creds.refresh(Request())
    return creds.token


def get_session(url: str) -> AuthorizedSession:
    """Sesión de `requests` que adjunta el ID token y lo renueva al expirar."""
    creds = _credentials(normalize_audience(url))
    if isinstance(creds, StaticCredentials):
        # Un token pre-emitido no se puede refrescar: un 401 se devuelve tal cual.
        return AuthorizedSession(creds, refresh_status_codes=())
    return AuthorizedSession(creds)
