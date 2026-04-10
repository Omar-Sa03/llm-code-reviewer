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
        f"*Confidence: {issue['confidence']:.0%}*"
    )


def annotate_diff(hunk_content: str, start_line: int) -> str:
    """Prefixes each line of the diff with its actual file line number."""
    lines = hunk_content.splitlines()
    annotated = []
    curr_line = start_line
    for line in lines:
        if line.startswith("+") or line.startswith(" "):
            annotated.append(f"{curr_line:4} | {line}")
            curr_line += 1
        elif line.startswith("-"):
            annotated.append(f"     | {line}")
        else:
            annotated.append(f"     | {line}")
    return "\n".join(annotated)


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

        annotated_content = annotate_diff(chunk.content, chunk.start_line)
        issues = review_chunk(annotated_content)
        print(f"[main]   → {len(issues)} raw issues found")

        for issue in issues:
            issue["file_path"] = chunk.file_path
            # The LLM now returns absolute line numbers as seen in the annotated diff
            issue["line"] = int(issue.get("line", chunk.start_line))

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