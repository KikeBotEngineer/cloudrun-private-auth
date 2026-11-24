import base64
import json

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="sample-api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/whoami")
def whoami(authorization: str | None = Header(default=None)):
    # ADVERTENCIA: el JWT se decodifica SIN verificar la firma. Es aceptable solo
    # porque Cloud Run ya lo verificó en su frontera (servicio sin
    # --allow-unauthenticated). No copiar esto a una API pública.
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Falta el header Authorization: Bearer <token>")
    try:
        payload = authorization.split()[1].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        raise HTTPException(400, "Token mal formado") from None
    return {"email": claims.get("email"), "aud": claims.get("aud")}
