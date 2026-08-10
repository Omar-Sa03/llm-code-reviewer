"""
Issue deduplicator — prevents re-posting the same comment on PR re-runs.

When a PR receives a force-push or an extra commit, the Action re-runs and
would normally re-post every comment. This module filters out issues that
already have a matching fingerprint in the PR's existing review comments.

Fingerprinting uses: file path + line number + first 120 chars of the
formatted comment body (stable across re-runs for the same model/prompt).
"""
from __future__ import annotations

import hashlib

from reviewer.logger import get_logger

log = get_logger(__name__)


def _format_comment_body(issue: dict) -> str:
    """Minimal formatting used only for fingerprinting (avoids circular import)."""
    icon = {"error": "🔴", "warning": "🟡", "suggestion": "💡"}.get(issue["severity"], "•")
    return (
        f"{icon} **{issue['category']}**\n\n"
        f"{issue['comment']}"
    )


def fingerprint_issue(issue: dict) -> str:
    """
    Generate a stable fingerprint for an issue.

    Matches the logic in ``github_client._fingerprint_comment`` so that
    existing PR comments and new issues are compared on the same basis.
    """
    body = _format_comment_body(issue)
    raw = f"{issue['file_path']}:{issue['line']}:{body[:120]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def deduplicate(
    issues: list[dict],
    existing_fingerprints: set[str],
) -> list[dict]:
    """
    Return only issues whose fingerprint is NOT already in ``existing_fingerprints``.

    Args:
        issues:                 Filtered list of issues to potentially post.
        existing_fingerprints:  Set returned by GitHubClient.get_existing_review_comments().

    Returns:
        Subset of ``issues`` that are genuinely new.
    """
    new_issues = []
    duplicates = 0
    for issue in issues:
        fp = fingerprint_issue(issue)
        if fp in existing_fingerprints:
            duplicates += 1
            log.info(
                "Skipping duplicate issue",
                extra={
                    "file_path":   issue["file_path"],
                    "line":        issue["line"],
                    "fingerprint": fp,
                },
            )
        else:
            new_issues.append(issue)

    log.info(
        "Deduplication complete",
        extra={
            "total":      len(issues),
            "duplicates": duplicates,
            "new":        len(new_issues),
        },
    )
    return new_issues
