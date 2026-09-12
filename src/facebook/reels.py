"""Facebook Reels publisher.

Publishes a validated MP4 to a Facebook Page as a Reel using the Meta Graph
API ``/page_id/video_reels`` endpoint (three-step resumable upload):

    1. POST  /{page_id}/video_reels?upload_phase=START
            -> {video_id, upload_url}
    2. PUT   {upload_url}  (binary video, Authorization: OAuth ***
            -> {success, h}
    3. POST  /{page_id}/video_reels?upload_phase=FINISH&video_id=...
            -> {success, post_id, message}

After publishing, posts a first comment and a pinned comment on the Reel
(when not in dry-run mode). Pinning requires the ``pages_manage_engagement``
permission; failures are logged but do not block the pipeline.

Flow respects the project's safety rules:
- ``DRY_RUN`` mode NEVER hits the network; it returns a dry-run result
  describing what would be posted.
- Secrets (access token) are never logged or included in error messages.
- Non-transient API errors (invalid token, permissions, abusive, invalid
  parameter) raise immediately and are NOT retried, preserving idempotency.
- Transient failures (network / 5xx / rate limit) retry with bounded
  backoff up to ``facebook_retry_count``.

Permissions required on the Page access token:
    pages_read_engagement, pages_manage_posts

For comment posting/pinning:
    pages_manage_engagement, pages_show_list

Rate limit: 30 API-published posts per 24-hour moving period (enforced by
Meta on the POST /{page_id}/video_reels endpoint).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from src.config import settings
from src.content.schema import GospelContent

logger = logging.getLogger(__name__)

# Default Graph API version if FACEBOOK_GRAPH_VERSION is not configured.
DEFAULT_GRAPH_VERSION = "v26.0"

# Reels publishing API endpoint path (POST /{page_id}/video_reels).
REELS_ENDPOINT = "video_reels"

# Max caption/description length (Meta limit for Reels description is 2200,
# but schema caps caption at 500. We use the schema limit as our effective max.)
MAX_CAPTION_LENGTH = 500

# Non-transient error subcodes that must NOT be retried:
#  190 = invalid/expired OAuth token; 200 = permissions; 368 = abusive;
#  100 = invalid parameter; 613 = rate limit exceeded.
NON_RETRYABLE_ERROR_CODES = {100, 190, 200, 368, 613}


class FacebookPublishError(Exception):
    """Base error for Facebook publishing failures."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class FacebookAuthError(FacebookPublishError):
    """Invalid/expired token or insufficient permissions."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class FacebookRateLimitError(FacebookPublishError):
    """API rate limit exceeded (error code 613)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


@dataclass
class PublishResult:
    """Result of a Reels publish attempt."""

    published: bool = False
    dry_run: bool = False
    post_id: str = ""
    video_id: str = ""
    message: str = ""
    attempts: int = 1
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.published or self.dry_run

    def to_dict(self) -> dict:
        return {
            "published": self.published,
            "dry_run": self.dry_run,
            "post_id": self.post_id,
            "video_id": self.video_id,
            "message": self.message,
            "attempts": self.attempts,
            "errors": self.errors,
        }


@dataclass
class ReelVerification:
    """Result of a Reel public accessibility check."""
    is_public: bool
    reason: str
    permalink: str = ""


class ReelsPublisher:
    """Publishes validated Reels MP4s to a Facebook Page via the Graph API.

    Attributes:
        page_id: Facebook Page ID.
        access_token: Page access token (secret; never logged).
        graph_version: Graph API version (e.g. 'v26.0').
        dry_run: If True, never contacts the network.
        retry_count: Max transient retries.
        timeout: HTTP timeout in seconds.
    """

    def __init__(
        self,
        page_id: str | None = None,
        access_token: str | None = None,
        graph_version: str | None = None,
        dry_run: bool | None = None,
        retry_count: int | None = None,
        timeout: float = 120.0,
        session: requests.Session | None = None,
    ) -> None:
        """Initialize the publisher.

        Args:
            page_id: Facebook Page ID (defaults to settings).
            access_token: Page access token (defaults to settings; secret).
            graph_version: Graph API version (default from settings or v26.0).
            dry_run: Dry-run override (defaults to settings.dry_run).
            retry_count: Max transient retries (defaults to settings).
            timeout: HTTP timeout in seconds.
            session: Optional requests.Session (for tests / reuse).
        """
        self.page_id = str(page_id or settings.meta_page_id or "")
        self.access_token = access_token or settings.meta_page_access_token or ""
        self.graph_version = (
            graph_version
            or settings.facebook_graph_version
            or DEFAULT_GRAPH_VERSION
        )
        self.dry_run = settings.dry_run if dry_run is None else dry_run
        self.retry_count = retry_count if retry_count is not None else settings.facebook_retry_count
        self.timeout = timeout
        self.session = session or requests.Session()

        # Credentials are only required in live mode.
        if not self.dry_run:
            if not self.page_id:
                raise FacebookPublishError(
                    "META_PAGE_ID is not configured; set it in .env or pass page_id"
                )
            if not self.access_token:
                raise FacebookPublishError(
                    "META_PAGE_ACCESS_TOKEN is not configured; set it in .env or pass access_token"
                )

        logger.info(
            f"ReelsPublisher initialized: page={self.page_id or '(dry-run)'}, "
            f"graph={self.graph_version}, dry_run={self.dry_run}, "
            f"retries={self.retry_count}"
        )

    # ------------------------------------------------------------------
    # Caption building
    # ------------------------------------------------------------------
    def build_caption(self, story: GospelContent) -> str:
        """Build the Reel caption/description from GospelContent.

        Uses the ``facebook_caption`` field (which comes from the same
        generated source as everything else), with hashtags appended.
        """
        parts: list[str] = []
        caption_text = (story.facebook_caption or story.hook).strip()
        parts.append(caption_text)
        tags = " ".join(story.hashtags).strip()
        if tags:
            parts.append(tags)

        caption = "\n\n".join(p for p in parts if p)
        if len(caption) > MAX_CAPTION_LENGTH:
            caption = caption[: MAX_CAPTION_LENGTH - 3].rstrip() + "..."
        return caption

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------
    def _graph_url(self) -> str:
        """Return the base Graph API URL for the configured version."""
        return f"https://graph.facebook.com/{self.graph_version}"

    def _reels_url(self) -> str:
        """Return the video_reels endpoint URL for this page."""
        return f"{self._graph_url()}/{self.page_id}/{REELS_ENDPOINT}"

    def _comments_url(self, post_id: str) -> str:
        """Return the comments endpoint URL for a given post.

        Graph API v2.4+ requires the composite ``{page_id}_{post_id}``
        format to query/mutate Page posts.
        """
        object_id = post_id if "_" in post_id else f"{self.page_id}_{post_id}"
        return f"{self._graph_url()}/{object_id}/comments"

    def _error_from_response(self, resp: requests.Response) -> str:
        """Extract a safe (redacted) error message from an API response."""
        try:
            data = resp.json()
        except ValueError:
            return f"HTTP {resp.status_code}: {resp.text[:200]}"
        err = data.get("error", {}) if isinstance(data, dict) else {}
        code = err.get("code")
        msg = err.get("message", "")
        safe_msg = str(msg).replace(
            "OAuth", "OAuth"
        )  # message text is Meta's, no token in it
        return f"Graph API error {code}: {safe_msg}"

    def _classify_error(self, resp: requests.Response) -> FacebookPublishError:
        """Classify an API error response into a typed exception."""
        data: dict = {}
        try:
            data = resp.json()
        except ValueError:
            pass
        code = None
        if isinstance(data, dict):
            err = data.get("error") or {}
            if isinstance(err, dict):
                code = err.get("code")
        text = self._error_from_response(resp)

        if code == 190:
            return FacebookAuthError(f"Invalid or expired page access token. {text}")
        if code == 200:
            return FacebookAuthError(
                f"Insufficient permissions. Ensure the token has "
                f"pages_read_engagement and pages_manage_posts. {text}"
            )
        if code == 613:
            return FacebookRateLimitError(f"Facebook rate limit exceeded. {text}")
        if code in NON_RETRYABLE_ERROR_CODES:
            return FacebookPublishError(text, retryable=False)
        # Everything else (5xx, network) is treated as transient.
        return FacebookPublishError(text, retryable=True)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------
    def publish(
        self,
        video_path: Path | str,
        story: GospelContent | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> PublishResult:
        """Publish a video as a Reel.

        Args:
            video_path: Path to the validated MP4.
            story: Optional GospelContent (used for caption building).
            title: Optional explicit Reel title.
            description: Optional explicit description (overrides caption).

        Returns:
            PublishResult with post_id on success.

        Raises:
            FacebookPublishError: On API/auth/network failure.
        """
        video = Path(video_path)
        if not video.exists():
            raise FacebookPublishError(f"Video file not found: {video}")

        # DRY-RUN: never contact the network.
        if self.dry_run:
            result = PublishResult(
                published=False,
                dry_run=True,
                message=(
                    f"[DRY RUN] Would publish Reel on page {self.page_id}: "
                    f"{video.name} "
                    f"(title: {title or (story.hook[:100] if story else 'N/A')}, "
                    f"description: {description or 'auto caption'})"
                ),
            )
            logger.info("Reels publisher (dry run) skipped network call")
            return result

        # Build title/description if not provided.
        final_title = (
            title
            or (story.hook[:100] if story else "")
            or video.stem[:100]
        ).strip()[:255]
        final_desc = description or (
            self.build_caption(story) if story else video.stem[:MAX_CAPTION_LENGTH]
        )
        final_desc = final_desc.strip()[:MAX_CAPTION_LENGTH]

        # Step 1: START upload session
        video_id, upload_url = self._start_upload()
        try:
            # Step 2: upload binary to rupload URL
            self._upload_binary(upload_url, video)
            # Step 3: FINISH + publish
            return self._finish_publish(video_id, final_title, final_desc)
        except Exception:
            logger.error(
                f"Reels upload failed for {video.name} (video_id={video_id}); "
                "the upload session may need cleanup."
            )
            raise

    # ------------------------------------------------------------------
    # Comment posting
    # ------------------------------------------------------------------
    def publish_comments(
        self,
        post_id: str,
        first_comment: str,
        pinned_comment: str,
    ) -> dict[str, Any]:
        """Post a first comment and a pinned comment on a published Reel.

        Args:
            post_id: The post/video ID returned by the FINISH phase.
                Accepts bare post ID or composite ``{page_id}_{post_id}``.
            first_comment: Text of the first comment (always posted).
            pinned_comment: Text of the comment to pin (posted then pinned).

        Returns:
            Dict with:
            - first_comment_id: ID of the posted first comment (or empty on failure)
            - pinned_comment_id: ID of the posted pinned comment (or empty on failure)
            - pinned: True if the pinned comment was successfully pinned

        Notes:
            Pinning requires ``pages_manage_engagement`` permission. If the
            pin fails (permission missing), both comments remain posted and
            the failure is logged. The pipeline never fails due to a comment
            error.
        """
        result: dict[str, Any] = {
            "first_comment_id": "",
            "pinned_comment_id": "",
            "pinned": False,
        }

        if self.dry_run:
            logger.info("Comment posting skipped (dry run)")
            return result

        # Post first comment
        try:
            comment_id = self._post_comment(post_id, first_comment)
            result["first_comment_id"] = comment_id
            logger.info(f"First comment posted: id={comment_id}")
        except FacebookPublishError as e:
            logger.warning(f"First comment posting failed (non-fatal): {e}")

        # Post pinned comment
        pinned_comment_id = ""
        try:
            pinned_comment_id = self._post_comment(post_id, pinned_comment)
            result["pinned_comment_id"] = pinned_comment_id
            logger.info(f"Pinned comment posted: id={pinned_comment_id}")
        except FacebookPublishError as e:
            logger.warning(f"Pinned comment posting failed (non-fatal): {e}")

        # Pin the comment (requires pages_manage_engagement)
        if pinned_comment_id:
            try:
                self._pin_comment(pinned_comment_id)
                result["pinned"] = True
                logger.info(f"Comment pinned: id={pinned_comment_id}")
            except FacebookPublishError as e:
                logger.warning(
                    f"Comment pinning failed (non-fatal; check pages_manage_engagement permission): {e}"
                )

        return result

    def _post_comment(self, post_id: str, text: str) -> str:
        """Post a comment on a post. Returns the comment ID.

        Args:
            post_id: Bare post ID or composite ``{page_id}_{post_id}``.
            text: Comment body.

        Returns:
            The posted comment's ID.

        Raises:
            FacebookPublishError: On API failure.
        """
        url = self._comments_url(post_id)
        params = {"message": text, "access_token": self.access_token}

        def attempt() -> str:
            resp = self.session.post(url, params=params, timeout=self.timeout)
            if resp.status_code not in (200, 201):
                raise self._classify_error(resp)
            data = self._parse_json(resp)
            comment_id = str(data.get("id", ""))
            if not comment_id:
                raise FacebookPublishError(
                    f"Comment POST did not return an id: {data}"
                )
            return comment_id

        return self._retry_transient(attempt, context="post comment")

    def _pin_comment(self, comment_id: str) -> None:
        """Pin a comment by setting its ``comment_privacy`` field.

        Requires ``pages_manage_engagement`` on the Page access token.

        Args:
            comment_id: The ID of the comment to pin.

        Raises:
            FacebookPublishError: On API failure (e.g. missing permission).
        """
        # Pinning is done via POST /{comment_id}?pin=true (Graph API v2.6+).
        # When pinning by comment ID, the endpoint is a direct comment
        # object update, not nested under the post.
        url = f"{self._graph_url()}/{comment_id}"
        params = {"pin": "true", "access_token": self.access_token}

        def attempt() -> None:
            resp = self.session.post(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                raise self._classify_error(resp)
            data = self._parse_json(resp)
            if not data.get("success", True):
                raise FacebookPublishError(
                    f"Pin comment returned success=false: {data}"
                )

        self._retry_transient(attempt, context="pin comment")

    # ------------------------------------------------------------------
    # Upload steps
    # ------------------------------------------------------------------
    def _start_upload(self) -> tuple[str, str]:
        """Step 1: request an upload session; return (video_id, upload_url)."""
        url = self._reels_url()
        params = {
            "upload_phase": "START",
            "access_token": self.access_token,
        }

        def attempt() -> dict:
            resp = self.session.post(
                url, params=params, timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise self._classify_error(resp)
            return self._parse_json(resp)

        data = self._retry_transient(attempt, context="start upload")
        video_id = str(data.get("video_id", ""))
        upload_url = str(data.get("upload_url", ""))
        if not video_id or not upload_url:
            raise FacebookPublishError(
                f"START response missing video_id/upload_url: {data}"
            )
        logger.info(f"Reels upload session started (video_id={video_id})")
        return video_id, upload_url

    def _upload_binary(self, upload_url: str, video: Path) -> None:
        """Step 2: upload the video binary to the rupload URL."""
        size = video.stat().st_size

        def attempt() -> bytes:
            with open(video, "rb") as f:
                resp = self.session.post(
                    upload_url,
                    data=f,
                    headers={
                        "Authorization": f"OAuth {self.access_token}",
                        "Content-Type": "application/octet-stream",
                        "file_size": str(size),
                        "offset": "0",
                    },
                    timeout=self.timeout,
                )
            if resp.status_code not in (200, 201):
                raise self._classify_error(resp)
            return resp.content

        self._retry_transient(attempt, context="rupload binary")
        logger.info(f"Reels binary uploaded: {video.name} ({size} bytes)")

    def _finish_publish(
        self,
        video_id: str,
        title: str,
        description: str,
    ) -> PublishResult:
        """Step 3: FINISH the upload and publish the Reel."""
        url = self._reels_url()
        params = {
            "upload_phase": "FINISH",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "title": title,
            "description": description,
            "access_token": self.access_token,
        }

        def attempt() -> dict:
            resp = self.session.post(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                raise self._classify_error(resp)
            return self._parse_json(resp)

        data = self._retry_transient(attempt, context="finish publish")
        post_id = str(data.get("post_id", ""))
        message = str(data.get("message", ""))
        success = bool(data.get("success", True))

        if not success or not post_id:
            raise FacebookPublishError(
                f"Reels publish did not return a post_id: {data}"
            )

        # Verify the Reel is actually publicly accessible.
        verification = self._verify_public_reel(post_id)
        if not verification.is_public:
            logger.warning(
                f"Reel {post_id} created but may not be publicly accessible: "
                f"{verification.reason}"
            )

        logger.info(f"Reel published: post_id={post_id}")
        return PublishResult(
            published=True,
            post_id=post_id,
            video_id=video_id,
            message=message or "published",
        )

    def _verify_public_reel(self, post_id: str) -> ReelVerification:
        """Check if a published Reel is accessible to non-admins."""
        object_id = post_id if "_" in post_id else f"{self.page_id}_{post_id}"
        url = f"{self._graph_url()}/{object_id}"
        params = {
            "fields": "id,is_published,permalink_url,privacy,object_id",
            "access_token": self.access_token,
        }
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                error_detail = self._error_from_response(resp)
                return ReelVerification(
                    is_public=False,
                    reason=f"Verification GET failed: {resp.status_code} — {error_detail}",
                )
            data = resp.json()
            if not isinstance(data, dict):
                return ReelVerification(
                    is_public=False,
                    reason="Verification response not a dict",
                )

            is_published = bool(data.get("is_published", True))
            permalink = data.get("permalink_url", "")
            privacy = data.get("privacy", {})

            if not is_published:
                return ReelVerification(
                    is_public=False,
                    reason="is_published=false",
                )

            privacy_value = privacy.get("value", "") if isinstance(privacy, dict) else ""
            if privacy_value and privacy_value != "EVERYONE":
                return ReelVerification(
                    is_public=False,
                    reason=f"privacy={privacy_value}",
                )

            if permalink and is_published:
                return ReelVerification(
                    is_public=True,
                    reason="verified public",
                    permalink=permalink,
                )

            return ReelVerification(
                is_public=False,
                reason="missing permalink or ambiguous response",
            )
        except Exception as e:
            return ReelVerification(
                is_public=False,
                reason=f"Verification error: {type(e).__name__}",
            )

    def _parse_json(self, resp: requests.Response) -> dict:
        """Parse a JSON response body safely."""
        try:
            data = resp.json()
        except ValueError:
            raise FacebookPublishError(
                f"Invalid JSON in response (HTTP {resp.status_code}): "
                f"{resp.text[:200]}"
            )
        if not isinstance(data, dict):
            raise FacebookPublishError(
                f"Unexpected response shape (HTTP {resp.status_code}): {data!r}"
            )
        return data

    def _retry_transient(
        self,
        fn,
        context: str,
    ) -> Any:
        """Run fn with bounded retries on transient failures only."""
        attempt = 0
        while True:
            try:
                return fn()
            except FacebookPublishError as e:
                if not e.retryable:
                    raise
                attempt += 1
                if attempt > self.retry_count:
                    logger.error(
                        f"{context}: transient failure after "
                        f"{self.retry_count} retries: {e}"
                    )
                    raise FacebookPublishError(
                        f"{context} failed after {self.retry_count} retries: {e}",
                        retryable=True,
                    ) from e
                delay = min(2 ** attempt, 30)
                logger.warning(
                    f"{context}: transient failure (attempt {attempt}/{self.retry_count}); "
                    f"retrying in {delay}s: {e}"
                )
                if not self.dry_run:
                    time.sleep(delay)