import hashlib
import logging

import pytest
import requests
from fastapi.testclient import TestClient
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from app.config import Settings, load_settings
from app.main import MAX_BODY_BYTES, create_app

KEY = "tester-secret-key"
UPSTREAM = "https://sample-api-xxxx.run.app"
SETTINGS = Settings(
    upstream_url=UPSTREAM,
    api_keys={"testers": hashlib.sha256(KEY.encode()).hexdigest()},
    allowed_routes=frozenset({("GET", "/whoami"), ("POST", "/echo")}),
    timeout=2,
)


class FakeUpstream(requests.adapters.BaseAdapter):
    """Simula la API privada a nivel de transporte y guarda lo que recibió."""

    def __init__(self, status=200, exc=None, headers=None):
        super().__init__()
        self.status, self.exc, self.headers, self.sent = status, exc, headers or {}, []

    def send(self, request, **kwargs):
        self.sent.append(request)
        if self.exc:
            raise self.exc
        resp = requests.Response()
        resp.status_code, resp._content, resp.url = self.status, b'{"ok": true}', request.url
        resp.request = request  # como en una respuesta real; requests lo usa en los 3xx
        resp.headers["Content-Type"] = "application/json"
        resp.headers.update(self.headers)
        return resp

    def close(self):
        pass


def make_client(upstream: FakeUpstream) -> TestClient:
    session = AuthorizedSession(Credentials(token="gateway-token"), refresh_status_codes=())
    session.mount("https://", upstream)
    return TestClient(create_app(SETTINGS, session))


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_missing_or_invalid_key_is_401(headers):
    upstream = FakeUpstream()
    assert make_client(upstream).get("/whoami", headers=headers).status_code == 401
    assert upstream.sent == []


@pytest.mark.parametrize("method,path", [("GET", "/admin"), ("DELETE", "/whoami")])
def test_route_not_allowed_is_404(method, path):
    upstream = FakeUpstream()
    resp = make_client(upstream).request(method, path, headers={"X-API-Key": KEY})
    assert resp.status_code == 404
    assert upstream.sent == []


def test_forwards_with_gateway_token_instead_of_client_authorization():
    upstream = FakeUpstream()
    resp = make_client(upstream).post(
        "/echo?a=1&a=2",
        content=b'{"x": 1}',
        headers={
            "X-API-Key": KEY,
            "Authorization": "Bearer injected-by-client",
            "X-Request-Id": "req-123",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    sent = upstream.sent[0]
    assert sent.url == f"{UPSTREAM}/echo?a=1&a=2"
    assert sent.headers["Authorization"] == "Bearer gateway-token"
    assert sent.headers["X-Request-Id"] == "req-123"
    assert "X-API-Key" not in sent.headers
    assert sent.body == b'{"x": 1}'


def test_oversized_body_is_413_and_not_forwarded():
    upstream = FakeUpstream()
    big = b"x" * (MAX_BODY_BYTES + 1)
    resp = make_client(upstream).post("/echo", content=big, headers={"X-API-Key": KEY})
    assert resp.status_code == 413
    assert upstream.sent == []


def test_key_checked_before_body():
    # Sin key válida se rechaza con 401 aunque el body exceda el límite.
    big = b"x" * (MAX_BODY_BYTES + 1)
    assert make_client(FakeUpstream()).post("/echo", content=big).status_code == 401


@pytest.mark.parametrize(
    "location,expected",
    [
        (f"{UPSTREAM}/whoami?x=1", "/whoami?x=1"),  # URL privada -> relativa
        (UPSTREAM, "/"),
        ("https://example.com/a", "https://example.com/a"),  # externa: tal cual
        (f"{UPSTREAM}.evil.com/a", f"{UPSTREAM}.evil.com/a"),  # no es prefijo real
    ],
)
def test_redirect_is_returned_not_followed(location, expected):
    upstream = FakeUpstream(status=302, headers={"Location": location})
    client = make_client(upstream)
    resp = client.get("/whoami", headers={"X-API-Key": KEY}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == expected
    assert len(upstream.sent) == 1  # el gateway no siguió la redirección


@pytest.mark.parametrize("status", [401, 403])
def test_upstream_rejects_gateway_is_502(status):
    resp = make_client(FakeUpstream(status=status)).get("/whoami", headers={"X-API-Key": KEY})
    assert resp.status_code == 502


def test_upstream_timeout_is_504():
    upstream = FakeUpstream(exc=requests.Timeout())
    assert make_client(upstream).get("/whoami", headers={"X-API-Key": KEY}).status_code == 504


def test_key_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    client = make_client(FakeUpstream())
    client.get("/whoami", headers={"X-API-Key": KEY})
    client.get("/whoami", headers={"X-API-Key": KEY + "x"})
    client.get("/admin", headers={"X-API-Key": KEY})
    assert "consumer=testers" in caplog.text
    assert KEY not in caplog.text


def test_load_settings():
    digest = "a" * 64
    s = load_settings(
        {
            "UPSTREAM_URL": UPSTREAM + "/",
            "API_KEYS": f"testers:{digest}, partner-a:{digest.upper()}",
            "ALLOWED_ROUTES": "GET /health, get /whoami",
            "UPSTREAM_TIMEOUT_SECONDS": "5",
        }
    )
    assert s.upstream_url == UPSTREAM
    assert s.api_keys == {"testers": digest, "partner-a": digest}
    assert s.allowed_routes == {("GET", "/health"), ("GET", "/whoami")}
    assert s.timeout == 5


@pytest.mark.parametrize(
    "env", [{"UPSTREAM_URL": UPSTREAM}, {"UPSTREAM_URL": UPSTREAM, "API_KEYS": "testers:short"}]
)
def test_load_settings_rejects_bad_config(env):
    with pytest.raises(RuntimeError):
        load_settings(env)
