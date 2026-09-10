"""Tests for the repository_dispatch trigger script."""

import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from scripts.trigger_pipeline import (
    API_BASE,
    DEFAULT_EVENT_TYPE,
    TriggerError,
    build_request,
    main,
    send_dispatch,
)


class TestBuildRequest:
    """Request construction."""

    def test_url_and_headers(self):
        req = build_request("owner/repo", "secret-token")
        assert req.full_url == f"{API_BASE}/repos/owner/repo/dispatches"
        assert req.method == "POST"
        # urllib normalizes header names to Title-Case; GitHub accepts any case.
        headers = {k.lower(): v for k, v in req.headers.items()}
        assert headers["authorization"] == "Bearer secret-token"
        assert headers["accept"] == "application/vnd.github+json"
        assert headers["content-type"] == "application/json"

    def test_body_has_event_type(self):
        req = build_request("owner/repo", "tok")
        body = json.loads(req.data.decode())
        assert body == {"event_type": DEFAULT_EVENT_TYPE}

    def test_client_payload_included(self):
        req = build_request(
            "owner/repo", "tok", client_payload={"dry_run": True}
        )
        body = json.loads(req.data.decode())
        assert body == {
            "event_type": DEFAULT_EVENT_TYPE,
            "client_payload": {"dry_run": True},
        }

    def test_token_never_in_url_or_body(self):
        req = build_request("owner/repo", "SECRET123")
        assert "SECRET123" not in req.full_url
        assert "SECRET123" not in req.data.decode()

    def test_invalid_repo_raises(self):
        with pytest.raises(ValueError):
            build_request("no-slash-here", "tok")

    def test_empty_token_raises(self):
        with pytest.raises(ValueError):
            build_request("owner/repo", "   ")


class TestSendDispatch:
    """HTTP behavior with mocked urllib."""

    @patch("scripts.trigger_pipeline.urllib.request.urlopen")
    def test_success_204(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 204
        resp.read.return_value = b""
        mock_urlopen.return_value.__enter__.return_value = resp

        msg = send_dispatch("owner/repo", "tok")
        assert "owner/repo" in msg

    @patch("scripts.trigger_pipeline.urllib.request.urlopen")
    def test_request_has_bearer_header(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 204
        mock_urlopen.return_value.__enter__.return_value = resp

        send_dispatch("owner/repo", "tok-abc")
        request = mock_urlopen.call_args[0][0]
        headers = {k.lower(): v for k, v in request.headers.items()}
        assert headers["authorization"] == "Bearer tok-abc"

    @patch("scripts.trigger_pipeline.urllib.request.urlopen")
    def test_403_bad_token_raises_trigger_error(self, mock_urlopen):
        err = urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
        err.read = MagicMock(return_value=b'{"message":"Bad credentials"}')
        mock_urlopen.side_effect = err

        with pytest.raises(TriggerError) as exc:
            send_dispatch("owner/repo", "bad-token")
        assert "403" in str(exc.value)
        # Token never leaks
        assert "bad-token" not in str(exc.value)

    @patch("scripts.trigger_pipeline.urllib.request.urlopen")
    def test_404_wrong_repo(self, mock_urlopen):
        err = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        err.read = MagicMock(return_value=b'{"message":"Not Found"}')
        mock_urlopen.side_effect = err

        with pytest.raises(TriggerError) as exc:
            send_dispatch("owner/repo", "tok")
        assert "404" in str(exc.value)

    @patch("scripts.trigger_pipeline.urllib.request.urlopen")
    def test_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("boom")
        with pytest.raises(TriggerError) as exc:
            send_dispatch("owner/repo", "tok")
        assert "Network error" in str(exc.value)


class TestMain:
    """CLI behavior."""

    def test_missing_args_usage_error(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2  # argparse usage error

    @patch("scripts.trigger_pipeline.send_dispatch", return_value="ok")
    def test_success_exit_0(self, mock_send):
        assert main(["--repo", "owner/repo", "--token", "tok"]) == 0

    @patch(
        "scripts.trigger_pipeline.send_dispatch",
        side_effect=TriggerError("boom"),
    )
    def test_trigger_error_exit_1(self, mock_send):
        assert main(["--repo", "owner/repo", "--token", "tok"]) == 1

    def test_invalid_payload_json_exit_1(self, capsys):
        rc = main(
            ["--repo", "owner/repo", "--token", "tok", "--payload", "{bad"]
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "not valid JSON" in captured.err