"""
GitHub API client with connection pooling, retry, and deduplication support.
"""
from __future__ import annotations

import os
import hashlib
from typing import TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from reviewer.logger import get_logger

if TYPE_CHECKING:
    from reviewer.config import Config

log = get_logger(__name__)

_GITHUB_API = "https://api.github.com"


def _make_session(token: str) -> requests.Session:
    """Create a requests Session with connection pooling and HTTP-level retries."""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    # Retry on transient network/server errors (does NOT retry on 422 or 4xx logic errors)
    retry_policy = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist={500, 502, 503, 504},
        allowed_methods={"GET", "POST", "PATCH"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_policy)
    session.mount("https://", adapter)
    return session


class GitHubClient:
    def __init__(self, cfg: "Config | None" = None):
        # Support legacy env-var usage (no Config) for backward compatibility
        token = (cfg.github_token if cfg else None) or os.environ["GITHUB_TOKEN"]
        repo  = (cfg.github_repository if cfg else None) or os.environ["GITHUB_REPOSITORY"]
        pr_no = (cfg.pr_number if cfg else None) or int(os.environ["PR_NUMBER"])

        self.repo      = repo
        self.pr_number = pr_no
        self._session  = _make_session(token)

    # ── Read operations ────────────────────────────────────────────────────

    def get_pr_diff(self) -> str:
        url = f"{_GITHUB_API}/repos/{self.repo}/pulls/{self.pr_number}"
        r = self._session.get(
            url,
            headers={"Accept": "application/vnd.github.v3.diff"},
            timeout=30,
        )
        r.raise_for_status()
        return r.text

    def get_pr_head_sha(self) -> str:
        url = f"{_GITHUB_API}/repos/{self.repo}/pulls/{self.pr_number}"
        r = self._session.get(url, timeout=15)
        r.raise_for_status()
        return r.json()["head"]["sha"]

    def get_existing_review_comments(self) -> set[str]:
        """
        Fetch all existing inline review comments on the PR and return a set of
        fingerprints ``"<path>:<line>:<category_hash>"``.

        Used by the deduplicator to avoid re-posting the same comment on re-runs.
        """
        url = f"{_GITHUB_API}/repos/{self.repo}/pulls/{self.pr_number}/comments"
        fingerprints: set[str] = set()
        page = 1

        while True:
            r = self._session.get(url, params={"per_page": 100, "page": page}, timeout=15)
            r.raise_for_status()
            comments = r.json()
            if not comments:
                break
            for c in comments:
                fp = _fingerprint_comment(c.get("path", ""), c.get("line") or 0, c.get("body", ""))
                fingerprints.add(fp)
            page += 1
            if len(comments) < 100:
                break

        log.info("Fetched existing comments", extra={"count": len(fingerprints)})
        return fingerprints

    # ── Write operations ───────────────────────────────────────────────────

    def post_review_comment(
        self, commit_sha: str, path: str, line: int, body: str
    ) -> bool:
        url = f"{_GITHUB_API}/repos/{self.repo}/pulls/{self.pr_number}/comments"
        payload = {
            "body":      body,
            "commit_id": commit_sha,
            "path":      path,
            "line":      line,
            "side":      "RIGHT",
        }
        r = self._session.post(url, json=payload, timeout=15)
        if r.status_code == 422:
            log.warning(
                "Review comment rejected (422)",
                extra={"path": path, "line": line, "detail": r.json()},
            )
            return False
        r.raise_for_status()
        return True

    def post_pr_comment(self, body: str) -> None:
        url = f"{_GITHUB_API}/repos/{self.repo}/issues/{self.pr_number}/comments"
        r = self._session.post(url, json={"body": body}, timeout=15)
        r.raise_for_status()


def _fingerprint_comment(path: str, line: int, body: str) -> str:
    """
    Stable fingerprint for an issue comment.

    Uses path + line + first 120 chars of body so that minor wording changes
    in a prompt version don't accidentally suppress a re-post of the same issue.
    """
    raw = f"{path}:{line}:{body[:120]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]