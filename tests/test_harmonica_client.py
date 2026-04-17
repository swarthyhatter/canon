import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from harmonica.client import HarmonicaClient, HarmonicaError


def make_response(status_code: int, json_body=None, headers=None):
    """Build a minimal httpx.Response-like mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_body or {}
    resp.text = str(json_body)
    return resp


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HARMONICA_API_KEY", "hm_live_testkey")
    return HarmonicaClient()


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------

class TestAuth:
    def test_bearer_token_sent_on_every_request(self, client):
        ok = make_response(200, {"id": "s1"})
        with patch.object(client._client, "request", return_value=ok) as mock_req:
            client.get_session("s1")
            _, kwargs = mock_req.call_args
            headers = client._client.headers  # set at construction time
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer hm_live_testkey"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("HARMONICA_API_KEY", "hm_live_envkey")
        c = HarmonicaClient()
        assert c.api_key == "hm_live_envkey"

    def test_api_key_from_constructor_overrides_env(self, monkeypatch):
        monkeypatch.setenv("HARMONICA_API_KEY", "hm_live_envkey")
        c = HarmonicaClient(api_key="hm_live_explicit")
        assert c.api_key == "hm_live_explicit"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_raises_on_4xx(self, client):
        err = make_response(404, {"error": "not found"})
        with patch.object(client._client, "request", return_value=err):
            with pytest.raises(HarmonicaError, match="HTTP 404"):
                client.get_session("missing")

    def test_raises_on_5xx(self, client):
        err = make_response(500, {"error": "server error"})
        with patch.object(client._client, "request", return_value=err):
            with pytest.raises(HarmonicaError, match="HTTP 500"):
                client.get_session("s1")

    def test_returns_json_on_200(self, client):
        ok = make_response(200, {"id": "s1", "status": "active"})
        with patch.object(client._client, "request", return_value=ok):
            result = client.get_session("s1")
        assert result == {"id": "s1", "status": "active"}


# ---------------------------------------------------------------------------
# Retry logic (429 rate limiting)
# ---------------------------------------------------------------------------

class TestRetry:
    def test_retries_on_429_then_succeeds(self, client):
        rate_limited = make_response(429, headers={"Retry-After": "0"})
        ok = make_response(200, {"id": "s1"})
        with patch.object(
            client._client, "request", side_effect=[rate_limited, ok]
        ):
            with patch("harmonica.client.time.sleep") as mock_sleep:
                result = client.get_session("s1")
        mock_sleep.assert_called_once_with(0)
        assert result == {"id": "s1"}

    def test_uses_retry_after_header(self, client):
        rate_limited = make_response(429, headers={"Retry-After": "5"})
        ok = make_response(200, {"id": "s1"})
        with patch.object(
            client._client, "request", side_effect=[rate_limited, ok]
        ):
            with patch("harmonica.client.time.sleep") as mock_sleep:
                client.get_session("s1")
        mock_sleep.assert_called_once_with(5)

    def test_falls_back_to_exponential_backoff(self, client):
        rate_limited = make_response(429, headers={})
        ok = make_response(200, {"id": "s1"})
        with patch.object(
            client._client, "request", side_effect=[rate_limited, ok]
        ):
            with patch("harmonica.client.time.sleep") as mock_sleep:
                client.get_session("s1")
        # attempt 0 → 2**0 = 1
        mock_sleep.assert_called_once_with(1)

    def test_raises_after_max_retries(self, client):
        rate_limited = make_response(429, headers={"Retry-After": "0"})
        with patch.object(
            client._client,
            "request",
            side_effect=[rate_limited, rate_limited, rate_limited],
        ):
            with patch("harmonica.client.time.sleep"):
                with pytest.raises(
                    HarmonicaError, match="Max retries exceeded"
                ):
                    client.get_session("s1")

    def test_does_not_sleep_on_last_attempt(self, client):
        rate_limited = make_response(429, headers={"Retry-After": "0"})
        with patch.object(
            client._client,
            "request",
            side_effect=[rate_limited, rate_limited, rate_limited],
        ):
            with patch("harmonica.client.time.sleep") as mock_sleep:
                with pytest.raises(HarmonicaError):
                    client.get_session("s1")
        # only 2 sleeps — not on the final attempt
        assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# create_session payload
# ---------------------------------------------------------------------------

class TestCreateSession:
    def test_required_fields_sent(self, client):
        ok = make_response(200, {"id": "s1"})
        with patch.object(
            client._client, "request", return_value=ok
        ) as mock_req:
            client.create_session(topic="Test", goal="Learn things")
        _, kwargs = mock_req.call_args
        body = kwargs["json"]
        assert body["topic"] == "Test"
        assert body["goal"] == "Learn things"
        assert body["cross_pollination"] is False

    def test_optional_fields_omitted_when_none(self, client):
        ok = make_response(200, {"id": "s1"})
        with patch.object(
            client._client, "request", return_value=ok
        ) as mock_req:
            client.create_session(topic="Test", goal="Learn things")
        _, kwargs = mock_req.call_args
        body = kwargs["json"]
        assert "prompt" not in body
        assert "questions" not in body
        assert "summary_prompt" not in body

    def test_optional_fields_included_when_provided(self, client):
        ok = make_response(200, {"id": "s1"})
        with patch.object(
            client._client, "request", return_value=ok
        ) as mock_req:
            client.create_session(
                topic="Test",
                goal="Learn",
                prompt="Be helpful",
                questions=[{"text": "Q1"}],
                cross_pollination=True,
            )
        _, kwargs = mock_req.call_args
        body = kwargs["json"]
        assert body["prompt"] == "Be helpful"
        assert body["questions"] == [{"text": "Q1"}]
        assert body["cross_pollination"] is True
