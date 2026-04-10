import os
import sys
from reviewer.github_client      import GitHubClient
from reviewer.diff_parser        import parse_diff, should_skip
from reviewer.llm_client         import review_chunk
from reviewer.confidence_filter  import filter_issues
from reviewer.prompt             import build_summary


def format_comment(issue: dict) -> str:
    icon = {"error": "🔴", "warning": "🟡", "suggestion": "🔵"}.get(
        issue["severity"], "•"
    )
    return (
        f"{icon} **{issue['severity'].upper()}** · `{issue['category']}` · "
        f"`{issue['file_path']}`\n\n"
        f"{issue['comment']}\n\n"
        f"*Confidence: {issue['confidence']:.0%} "
    )


def map_to_local_line(hunk_content: str, relative_line: int, start_line: int) -> int:
    """Calculates the real file line number for a given hunk relative index."""
    lines = hunk_content.splitlines()
    new_file_line = start_line
    for i, line in enumerate(lines):
        if i + 1 == relative_line:
            return new_file_line
        if not line.startswith("-"):
            new_file_line += 1
    return new_file_line


def main():
    gh = GitHubClient()

    print("[main] Fetching PR diff...")
    raw_diff = gh.get_pr_diff()

    print("[main] Fetching PR head SHA...")
    commit_sha = os.environ.get("PR_SHA") or gh.get_pr_head_sha()

    all_issues:    list[dict] = []
    files_reviewed: int = 0
    skipped:        int = 0

    for chunk in parse_diff(raw_diff):
        if should_skip(chunk.file_path):
            print(f"[main] Skipping {chunk.file_path}")
            skipped += 1
            continue

        print(f"[main] Reviewing {chunk.file_path} (starts at line {chunk.start_line})...")
        files_reviewed += 1

        issues = review_chunk(chunk.content)
        print(f"[main]   → {len(issues)} raw issues found")

        for issue in issues:
            issue["file_path"] = chunk.file_path
            relative_line = max(1, int(issue.get("line", 1)))
            issue["line"] = map_to_local_line(chunk.content, relative_line, chunk.start_line)

        all_issues.extend(issues)

    print(f"[main] Total raw issues: {len(all_issues)}")
    kept = filter_issues(all_issues)
    print(f"[main] Issues after filtering: {len(kept)}")

    for issue in kept:
        body = format_comment(issue)
        success = gh.post_review_comment(
            commit_sha=commit_sha,
            path=issue["file_path"],
            line=issue["line"],
            body=body,
        )
        if not success:
            gh.post_pr_comment(body)

    summary = build_summary(kept, files_reviewed, skipped)
    gh.post_pr_comment(summary)
    print("[main] Done.")


if __name__ == "__main__":
    main()