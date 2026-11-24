import base64
import json

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def jwt(payload) -> str:
    """JWT sin firma válida: la API no la verifica (lo hace Cloud Run en su frontera)."""
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{body}.firma"


def whoami(authorization=None):
    headers = {"Authorization": authorization} if authorization is not None else {}
    return client.get("/whoami", headers=headers)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_whoami_returns_email_and_aud():
    token = jwt({"email": "ci@p.iam.gserviceaccount.com", "aud": "https://x.run.app", "x": 1})
    resp = whoami(f"Bearer {token}")
    assert resp.status_code == 200
    assert resp.json() == {"email": "ci@p.iam.gserviceaccount.com", "aud": "https://x.run.app"}


@pytest.mark.parametrize("authorization", [None, "", "Basic abc", "Bearer"])
def test_whoami_without_bearer_is_401(authorization):
    assert whoami(authorization).status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        "sin-puntos",
        "a.@@@.c",  # no es base64
        "a.bm8tanNvbg.c",  # base64 de "no-json"
        "a.//79.c",  # bytes que no son UTF-8
        jwt([1, 2]),  # JSON válido pero no es un objeto
        jwt("texto"),
    ],
)
def test_whoami_malformed_token_is_400(token):
    assert whoami(f"Bearer {token}").status_code == 400
