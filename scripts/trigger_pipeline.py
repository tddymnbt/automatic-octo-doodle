#!/usr/bin/env python3
"""Trigger the ASMR pipeline via a GitHub repository_dispatch event.

Fires ``POST /repos/{owner}/{repo}/dispatches`` with ``event_type:
trigger-pipeline`` — the same event cron-job.org sends on schedule, and the
manual "publish now" tool.

Usage:
    python scripts/trigger_pipeline.py --repo owner/repo --token "$GITHUB_PAT"
    python scripts/trigger_pipeline.py --repo owner/repo --token "$GITHUB_PAT" \
        --payload '{"dry_run": true}'

Exit codes:
    0 - Dispatch event accepted (HTTP 204)
    1 - Missing arguments / bad token / network error / non-204 response

The token is NEVER printed, logged, or placed in the URL or body.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.github.com"
DEFAULT_EVENT_TYPE = "trigger-pipeline"


class TriggerError(Exception):
    """Raised when the repository dispatch event could not be sent."""


def build_request(
    repo: str,
    token: str,
    event_type: str = DEFAULT_EVENT_TYPE,
    client_payload: dict[str, Any] | None = None,
) -> urllib.request.Request:
    """Build the POST request for the GitHub repository dispatch API.

    The token goes ONLY in the Authorization header — never in the URL,
    body, or returned error text.

    Args:
        repo: ``owner/repo`` slug.
        token: GitHub PAT (classic ``repo`` scope, or fine-grained with
            Contents: write on the repo).
        event_type: The custom event type the workflow listens for.
        client_payload: Optional extra data passed to the workflow.

    Returns:
        A configured urllib Request.

    Raises:
        ValueError: If repo or token look malformed/empty.
    """
    repo = repo.strip().strip("/")
    if "/" not in repo:
        raise ValueError("--repo must be in the form 'owner/repo'")
    if not token.strip():
        raise ValueError("--token must not be empty")

    url = f"{API_BASE}/repos/{repo}/dispatches"
    body: dict[str, Any] = {"event_type": event_type}
    if client_payload:
        body["client_payload"] = client_payload

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    return request


def send_dispatch(
    repo: str,
    token: str,
    event_type: str = DEFAULT_EVENT_TYPE,
    client_payload: dict[str, Any] | None = None,
) -> str:
    """Send the repository_dispatch event.

    Args:
        repo: ``owner/repo`` slug.
        token: GitHub PAT.
        event_type: Custom event type.
        client_payload: Optional payload.

    Returns:
        A human-readable success message.

    Raises:
        TriggerError: On HTTP/network failures. The token never appears.
    """
    try:
        request = build_request(repo, token, event_type, client_payload)
    except ValueError as e:
        raise TriggerError(str(e)) from e

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise TriggerError(f"Network error: {e.reason}") from e

    if status == 204:
        return (
            f"Repository dispatch sent to '{repo}' "
            f"(event_type={event_type})."
        )

    detail = _extract_error_detail(body)
    raise TriggerError(
        f"GitHub API returned HTTP {status}: {detail} "
        f"(check --repo and token scope - repo/Contents:write needed)"
    )


def _extract_error_detail(body: str) -> str:
    """Extract a concise, safe error detail from a GitHub API response."""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            message = data.get("message")
            if message:
                return str(message)
    except (json.JSONDecodeError, AttributeError):
        pass
    # Fall back to a truncated safe excerpt (never includes the token).
    excerpt = " ".join(body.split())[:200]
    return excerpt or "(empty response)"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Trigger the ASMR pipeline via GitHub repository_dispatch. "
            "The token is never printed."
        )
    )
    parser.add_argument("--repo", required=True, help="owner/repo GitHub slug")
    parser.add_argument(
        "--token",
        required=True,
        help="GitHub PAT (classic repo scope, or fine-grained Contents:write)",
    )
    parser.add_argument("--event-type", default=DEFAULT_EVENT_TYPE)
    parser.add_argument(
        "--payload",
        default=None,
        help='Optional JSON client_payload, e.g. \'{"dry_run": true}\'',
    )

    args = parser.parse_args(argv)

    client_payload: dict[str, Any] | None = None
    if args.payload:
        try:
            client_payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"ERROR: --payload is not valid JSON: {e}", file=sys.stderr)
            return 1

    try:
        message = send_dispatch(
            repo=args.repo,
            token=args.token,
            event_type=args.event_type,
            client_payload=client_payload,
        )
    except TriggerError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"✓ {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())