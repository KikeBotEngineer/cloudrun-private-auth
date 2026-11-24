from unittest import mock

import pytest

import identity_token

URL = "https://sample-api-xxxx.run.app/whoami?x=1"
AUD = "https://sample-api-xxxx.run.app"


class FakeCreds:
    def __init__(self, token):
        self.token, self.valid = None, False
        self._next = token

    def refresh(self, request):
        self.token, self.valid = self._next, True


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("GCP_ID_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    return monkeypatch


@pytest.fixture
def fetch():
    """google-auth: resuelve GOOGLE_APPLICATION_CREDENTIALS y, si no, el metadata server."""
    with mock.patch.object(
        identity_token.id_token,
        "fetch_id_token_credentials",
        return_value=FakeCreds("from-google-auth"),
    ) as m:
        yield m


def test_preissued_token_wins(env, fetch):
    env.setenv("GCP_ID_TOKEN", "pre-issued")
    env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/k.json")
    assert identity_token.get_token(URL) == "pre-issued"
    fetch.assert_not_called()


def test_without_preissued_token_delegates_to_google_auth(env, fetch):
    assert identity_token.get_token(URL) == "from-google-auth"
    assert fetch.call_args.args[0] == AUD


def test_key_file_is_honored_end_to_end(env, tmp_path):
    # Sin parchear fetch_id_token_credentials: comprueba que google-auth lee la variable.
    key = tmp_path / "k.json"
    key.write_text('{"type": "service_account"}')
    env.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key))
    with mock.patch(
        "google.oauth2.service_account.IDTokenCredentials.from_service_account_info",
        return_value=FakeCreds("from-key"),
    ) as from_info:
        assert identity_token.get_token(URL) == "from-key"
    assert from_info.call_args.kwargs["target_audience"] == AUD


@pytest.mark.parametrize(
    "bad", ["http://sample-api.run.app", "sample-api.run.app", "https://", "", "ftp://x"]
)
def test_invalid_audience(env, bad):
    with pytest.raises(ValueError):
        identity_token.get_token(bad)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://user:pass@sample-api.run.app/x", "https://sample-api.run.app"),
        ("https://sample-api.run.app:443/x", "https://sample-api.run.app"),
        ("https://Sample-API.run.app", "https://sample-api.run.app"),
        ("https://api.example.com:8443/x", "https://api.example.com:8443"),
    ],
)
def test_normalize_audience(url, expected):
    assert identity_token.normalize_audience(url) == expected


def test_invalid_audience_error_hides_credentials():
    with pytest.raises(ValueError) as exc:
        identity_token.normalize_audience("http://user:s3cret@sample-api.run.app")
    assert "s3cret" not in str(exc.value)


def test_session_with_preissued_token_does_not_refresh(env):
    env.setenv("GCP_ID_TOKEN", "pre-issued")
    session = identity_token.get_session(URL)
    assert session.credentials.token == "pre-issued"
    assert session._refresh_status_codes == ()
