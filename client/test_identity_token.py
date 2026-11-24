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
def key_file():
    with mock.patch.object(
        identity_token.service_account.IDTokenCredentials,
        "from_service_account_file",
        return_value=FakeCreds("from-key"),
    ) as m:
        yield m


@pytest.fixture
def metadata():
    with mock.patch.object(
        identity_token.id_token,
        "fetch_id_token_credentials",
        return_value=FakeCreds("from-metadata"),
    ) as m:
        yield m


def test_preissued_token_wins(env, key_file, metadata):
    env.setenv("GCP_ID_TOKEN", "pre-issued")
    env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/k.json")
    assert identity_token.get_token(URL) == "pre-issued"
    key_file.assert_not_called()
    metadata.assert_not_called()


def test_key_file_before_metadata(env, key_file, metadata):
    env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/k.json")
    assert identity_token.get_token(URL) == "from-key"
    key_file.assert_called_once_with("/k.json", target_audience=AUD)
    metadata.assert_not_called()


def test_metadata_as_fallback(env, key_file, metadata):
    assert identity_token.get_token(URL) == "from-metadata"
    assert metadata.call_args.args[0] == AUD
    key_file.assert_not_called()


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
