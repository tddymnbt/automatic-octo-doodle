"""Tests for the Facebook Reels publisher."""

from unittest.mock import MagicMock, patch

import pytest

from src.content.schema import Scene, StoryData
from src.facebook.reels import (
    MAX_CAPTION_LENGTH,
    FacebookAuthError,
    FacebookPublishError,
    FacebookRateLimitError,
    PublishResult,
    ReelsPublisher,
)


def make_story(**overrides) -> StoryData:
    """Create a realistic StoryData for test purposes."""
    defaults = {
        "title": "The Midnight Clockmaker",
        "hook": "The old clockmaker wound the key one last time...",
        "narration": (
            "The old clockmaker wound the key one last time, "
            "and the silence of midnight seemed to listen."
        ),
        "scenes": [
            Scene(description="bedroom", duration_seconds=3.0, category="bedroom")
        ],
        "caption": "A calm story about midnight clocks and quiet secrets.",
        "hashtags": ["#ASMR", "#MidnightStory", "#CalmNarration"],
    }
    defaults.update(overrides)
    return StoryData(**defaults)


# ------------------------------------------------------------------


class TestPublishResult:
    """Test PublishResult dataclass."""

    def test_success_when_published(self):
        r = PublishResult(published=True, post_id="123")
        assert r.success is True

    def test_success_when_dry_run(self):
        r = PublishResult(dry_run=True, message="skipped")
        assert r.success is True

    def test_not_success(self):
        r = PublishResult()
        assert r.success is False

    def test_to_dict(self):
        r = PublishResult(published=True, post_id="abc", dry_run=False)
        d = r.to_dict()
        assert d["post_id"] == "abc"
        assert d["published"] is True
        assert d["dry_run"] is False


class TestBuildCaption:
    """Test caption building."""

    def test_uses_caption_when_present(self):
        pub = ReelsPublisher.__new__(ReelsPublisher)
        pub.access_token = "tok"
        story = make_story(caption="A beautiful story.", hashtags=["#a", "#b"])
        cap = pub.build_caption(story)
        assert "A beautiful story." in cap
        assert "#a" in cap and "#b" in cap

    def test_falls_back_to_title_when_no_caption(self):
        pub = ReelsPublisher.__new__(ReelsPublisher)
        pub.access_token = "tok"
        story = make_story(caption="", title="My Story", hashtags=[])
        cap = pub.build_caption(story)
        assert "My Story" in cap

    def test_caption_is_capped(self):
        pub = ReelsPublisher.__new__(ReelsPublisher)
        pub.access_token = "tok"
        # MAX_CAPTION_LENGTH == 500 (same as schema), so test with exactly 500
        story = make_story(caption="x" * MAX_CAPTION_LENGTH, hashtags=[])
        cap = pub.build_caption(story)
        assert len(cap) <= MAX_CAPTION_LENGTH
        assert cap == "x" * MAX_CAPTION_LENGTH  # no truncation when at limit

        # Test that when combined with hashtags it still respects limit
        # (cap gets truncated if over MAX_CAPTION_LENGTH after adding hashtags)
        story = make_story(caption="x" * (MAX_CAPTION_LENGTH - 50), hashtags=["#" + "y" * 60])
        cap = pub.build_caption(story)
        assert len(cap) <= MAX_CAPTION_LENGTH
        assert cap.endswith("...")

    def test_hashtags_newline_separated(self):
        pub = ReelsPublisher.__new__(ReelsPublisher)
        pub.access_token = "tok"
        story = make_story(caption="A story.", hashtags=["#x", "#y"])
        cap = pub.build_caption(story)
        assert cap.startswith("A story.")
        assert "#x #y" in cap


class TestDryRun:
    """Test dry-run mode never hits the network."""

    def test_dry_run_skips_network(self, tmp_path):
        video = tmp_path / "final.mp4"
        video.write_bytes(b"fake video data")
        story = make_story()
        pub = ReelsPublisher(dry_run=True, page_id="", access_token="")
        result = pub.publish(video_path=video, story=story)
        assert result.dry_run is True
        assert result.published is False
        assert result.post_id == ""
        assert "DRY RUN" in result.message
        assert video.name in result.message

    def test_dry_run_no_credentials_needed(self, tmp_path):
        """dry_run mode should NOT require META_PAGE_ID or TOKEN."""
        pub = ReelsPublisher(dry_run=True, page_id="", access_token="")
        assert pub.page_id == ""
        assert pub.access_token == ""

    def test_dry_run_requires_video_file(self, tmp_path):
        pub = ReelsPublisher(dry_run=True, page_id="", access_token="")
        with pytest.raises(FacebookPublishError, match="not found"):
            pub.publish(video_path=tmp_path / "missing.mp4")


class TestCredentialValidation:
    """Test that live mode requires credentials."""

    def test_live_mode_requires_page_id(self):
        with pytest.raises(FacebookPublishError, match="META_PAGE_ID"):
            ReelsPublisher(dry_run=False, page_id="", access_token="tok")

    def test_live_mode_requires_token(self):
        with pytest.raises(FacebookPublishError, match="META_PAGE_ACCESS_TOKEN"):
            ReelsPublisher(dry_run=False, page_id="123", access_token="")

    def test_live_mode_passes_with_both(self):
        pub = ReelsPublisher(dry_run=False, page_id="123", access_token="tok")
        assert pub.page_id == "123"
        assert pub.access_token == "tok"


class TestGraphEndpoints:
    """Test URL construction."""

    def test_graph_url(self):
        pub = ReelsPublisher.__new__(ReelsPublisher)
        pub.graph_version = "v26.0"
        assert pub._graph_url() == "https://graph.facebook.com/v26.0"

    def test_reels_url(self):
        pub = ReelsPublisher.__new__(ReelsPublisher)
        pub.graph_version = "v26.0"
        pub.page_id = "98765"
        expected = "https://graph.facebook.com/v26.0/98765/video_reels"
        assert pub._reels_url() == expected


class TestLivePublish:
    """Test the three-step live publish flow (all network mocked)."""

    def _publisher(self, tmp_path, retry_count: int = 0) -> ReelsPublisher:
        return ReelsPublisher(
            dry_run=False,
            page_id="PAGE123",
            access_token="tok_secret_123",
            graph_version="v26.0",
            retry_count=retry_count,
            session=MagicMock(),
        )

    def test_publish_three_steps(self, tmp_path):
        """Happy path: START → rupload → FINISH → post_id."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake mp4 content")
        story = make_story()

        # Mock the three HTTP calls in order.
        mock_session = pub.session
        start_resp = MagicMock(status_code=200)
        start_resp.json.return_value = {
            "video_id": "VID001",
            "upload_url": "https://rupload.facebook.com/video-upload/v26.0/VID001",
            "success": True,
        }
        upload_resp = MagicMock(status_code=200)
        upload_resp.content = b"{}"
        finish_resp = MagicMock(status_code=200)
        finish_resp.json.return_value = {
            "success": True,
            "post_id": "POST456",
            "message": "published",
        }

        mock_session.post.side_effect = [start_resp, finish_resp]
        mock_session.put.return_value = upload_resp

        result = pub.publish(video_path=video, story=story)

        assert result.published is True
        assert result.post_id == "POST456"
        assert result.video_id == "VID001"
        assert mock_session.post.call_count == 2
        mock_session.put.assert_called_once()
        put_args = mock_session.put.call_args
        assert "rupload.facebook.com" in put_args[0][0]
        assert "OAuth tok_secret_123" in put_args[1]["headers"]["Authorization"]

    def test_publish_custom_title_and_description(self, tmp_path):
        """Custom title and description override story-based caption."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        mock_session = pub.session
        start_resp = MagicMock(status_code=200)
        start_resp.json.return_value = {"video_id": "V2", "upload_url": "https://rupload.facebook.com/v2", "success": True}
        upload_resp = MagicMock(status_code=200)
        upload_resp.content = b"{}"
        finish_resp = MagicMock(status_code=200)
        finish_resp.json.return_value = {"success": True, "post_id": "P2", "message": "ok"}

        mock_session.post.side_effect = [start_resp, finish_resp]
        mock_session.put.return_value = upload_resp

        result = pub.publish(video_path=video, title="My Reel", description="Custom desc")
        assert result.published is True
        assert result.post_id == "P2"

        finish_call = mock_session.post.call_args_list[1]
        assert finish_call[1]["params"]["title"] == "My Reel"
        assert finish_call[1]["params"]["description"] == "Custom desc"

    def test_auth_error_raises_auth_error(self, tmp_path):
        """Invalid token (code 190) must raise FacebookAuthError, no retry."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        error_resp = MagicMock(status_code=400)
        error_resp.json.return_value = {
            "error": {"code": 190, "message": "OAuthException: Invalid access token"}
        }
        pub.session.post.return_value = error_resp

        with pytest.raises(FacebookAuthError, match="access token"):
            pub.publish(video_path=video)
        assert pub.session.post.call_count == 1  # no retry

    def test_permissions_error_raises_auth_error(self, tmp_path):
        """Code 200 must raise FacebookAuthError (permissions)."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        error_resp = MagicMock(status_code=400)
        error_resp.json.return_value = {
            "error": {"code": 200, "message": "Permission denied"}
        }
        pub.session.post.return_value = error_resp

        with pytest.raises(FacebookAuthError, match="permissions"):
            pub.publish(video_path=video)
        assert pub.session.post.call_count == 1  # no retry

    def test_rate_limit_raises_rate_limit_error(self, tmp_path):
        """Code 613 must raise FacebookRateLimitError."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        error_resp = MagicMock(status_code=429)
        error_resp.json.return_value = {
            "error": {"code": 613, "message": "rate limit exceeded"}
        }
        pub.session.post.return_value = error_resp

        with pytest.raises(FacebookRateLimitError, match="rate limit"):
            pub.publish(video_path=video)
        assert pub.session.post.call_count == 1

    def test_invalid_param_no_retry(self, tmp_path):
        """Code 100 must raise FacebookPublishError (non-retryable)."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        error_resp = MagicMock(status_code=400)
        error_resp.json.return_value = {
            "error": {"code": 100, "message": "Invalid parameter"}
        }
        pub.session.post.return_value = error_resp

        with pytest.raises(FacebookPublishError, match="Invalid parameter"):
            pub.publish(video_path=video)
        assert pub.session.post.call_count == 1  # no retry

    def test_transient_error_retries_then_fails(self, tmp_path):
        """Transient failure (5xx) retries then fails with proper message."""
        pub = self._publisher(tmp_path, retry_count=2)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        error_resp = MagicMock(status_code=500)
        error_resp.json.return_value = {
            "error": {"code": None, "message": "server error"}
        }
        error_resp.status_code = 500
        pub.session.post.return_value = error_resp

        with pytest.raises(FacebookPublishError, match="after 2 retries"):
            pub.publish(video_path=video)
        # 1 initial + 2 retries = 3 calls total
        assert pub.session.post.call_count == 3

    def test_start_missing_video_id_raises(self, tmp_path):
        """If START returns no video_id, raise."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        incomplete_resp = MagicMock(status_code=200)
        incomplete_resp.json.return_value = {"success": True}  # missing video_id
        pub.session.post.return_value = incomplete_resp

        with pytest.raises(FacebookPublishError, match="missing video_id"):
            pub.publish(video_path=video)

    def test_finish_missing_post_id_raises(self, tmp_path):
        """If FINISH returns no post_id, raise."""
        pub = self._publisher(tmp_path)
        video = tmp_path / "reel.mp4"
        video.write_bytes(b"fake")

        start_resp = MagicMock(status_code=200)
        start_resp.json.return_value = {"video_id": "V3", "upload_url": "https://rupload.facebook.com/v3", "success": True}
        upload_resp = MagicMock(status_code=200)
        upload_resp.content = b"{}"
        finish_resp = MagicMock(status_code=200)
        finish_resp.json.return_value = {"success": True}  # missing post_id

        pub.session.post.side_effect = [start_resp, finish_resp]
        pub.session.put.return_value = upload_resp

        with pytest.raises(FacebookPublishError, match="post_id"):
            pub.publish(video_path=video)


class TestSecretsNeverLeaked:
    """Security: access token must never appear in error messages."""

    def test_auth_error_no_token_leak(self, tmp_path):
        pub = ReelsPublisher(dry_run=False, page_id="1", access_token="super_secret_token_xyz")
        resp = MagicMock(status_code=400)
        resp.json.return_value = {"error": {"code": 190, "message": "OAuthException: Invalid token"}}
        err = pub._classify_error(resp)
        msg = str(err)
        assert "super_secret_token_xyz" not in msg
        assert "OAuthException" in msg  # Meta's own message text is fine

    def test_auth_error_redacts_token_from_non_json_response(self, tmp_path):
        pub = ReelsPublisher(dry_run=False, page_id="1", access_token="tok123")
        resp = MagicMock(status_code=500)
        resp.json.side_effect = ValueError
        resp.text = "Internal Server Error"
        err = pub._classify_error(resp)
        assert "tok123" not in str(err)


class TestFactoryDefaults:
    """Test that ReelsPublisher picks up settings defaults."""

    def test_default_graph_version(self):
        """Should default to v26.0 when config is empty."""
        with patch("src.facebook.reels.settings") as mock_settings:
            mock_settings.meta_page_id = "1"
            mock_settings.meta_page_access_token = "tok"
            mock_settings.facebook_graph_version = ""
            mock_settings.dry_run = True
            mock_settings.facebook_retry_count = 3
            pub = ReelsPublisher()
            assert pub.graph_version == "v26.0"

    def test_uses_config_values(self):
        """Should prefer settings when no explicit args."""
        with patch("src.facebook.reels.settings") as mock_settings:
            mock_settings.meta_page_id = "PAGE42"
            mock_settings.meta_page_access_token = "config_tok"
            mock_settings.facebook_graph_version = "v24.0"
            mock_settings.dry_run = True
            mock_settings.facebook_retry_count = 5
            pub = ReelsPublisher()
            assert pub.page_id == "PAGE42"
            assert pub.graph_version == "v24.0"
            assert pub.retry_count == 5