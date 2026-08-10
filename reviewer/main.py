"""
LLM Code Reviewer — main pipeline.

Flow:
    load config
    → fetch PR diff + head SHA
    → fetch existing review comments (for deduplication)
    → for each diff chunk:
          skip if in blocklist
          estimate token cost (skip if over budget)
          call LLM (with retry + fallback)
          record metrics
    → filter by confidence + per-file caps
    → deduplicate against existing comments
    → post inline review comments (fall back to PR comment on 422)
    → post summary comment
    → write review_metrics.json artifact
"""
from __future__ import annotations

from reviewer.confidence_filter import filter_issues
from reviewer.config import load_config
from reviewer.cost_estimator import estimate_cost
from reviewer.deduplicator import deduplicate
from reviewer.diff_parser import parse_diff, should_skip
from reviewer.github_client import GitHubClient
from reviewer.llm_client import _estimate_tokens, review_chunk
from reviewer.logger import configure as configure_logger
from reviewer.logger import get_logger
from reviewer.metrics import Metrics
from reviewer.prompt import build_summary


def format_comment(issue: dict) -> str:
    icon = {"error": "🔴", "warning": "🟡", "suggestion": "💡"}.get(
        issue["severity"], "•"
    )
    return (
        f"{icon} **{issue['category']}**\n\n"
        f"{issue['comment']}"
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
        else:
            annotated.append(f"     | {line}")
    return "\n".join(annotated)


def main() -> None:
    cfg = load_config()
    configure_logger(run_id=cfg.run_id, model=cfg.model_name)
    log = get_logger(__name__)
    metrics = Metrics(
        run_id=cfg.run_id,
        model=cfg.model_name,
        provider=cfg.provider,
        prompt_version=cfg.prompt_version,
    )

    log.info("Reviewer started", extra={
        "model": cfg.model_name,
        "provider": cfg.provider,
        "prompt_version": cfg.prompt_version,
        "pr_number": cfg.pr_number,
    })

    gh = GitHubClient(cfg=cfg)

    log.info("Fetching PR diff")
    raw_diff = gh.get_pr_diff()

    commit_sha = cfg.pr_sha or gh.get_pr_head_sha()
    log.info("Using commit SHA", extra={"sha": commit_sha})

    log.info("Fetching existing review comments for deduplication")
    existing_fingerprints = gh.get_existing_review_comments()

    all_issues:     list[dict] = []
    files_reviewed: int = 0
    skipped:        int = 0
    total_estimated_cost: float = 0.0

    for chunk in parse_diff(raw_diff):
        if should_skip(chunk.file_path):
            log.info("Skipping file", extra={"file_path": chunk.file_path})
            skipped += 1
            continue

        log.info("Reviewing chunk", extra={
            "file_path":  chunk.file_path,
            "start_line": chunk.start_line,
        })
        files_reviewed += 1

        annotated_content = annotate_diff(chunk.content, chunk.start_line)
        token_estimate = _estimate_tokens(annotated_content)
        cost = estimate_cost(cfg.model_name, token_estimate)
        total_estimated_cost += cost

        raw_issues: list[dict] = []
        try:
            with metrics.time_llm_call(chunk.file_path):
                raw_issues = review_chunk(annotated_content, cfg)
        except Exception as exc:
            log.error("Unexpected error reviewing chunk", extra={
                "file_path": chunk.file_path,
                "error": str(exc),
            })
            metrics.record_llm_error(chunk.file_path)

        log.info("Raw issues found", extra={
            "file_path":      chunk.file_path,
            "raw_issues":     len(raw_issues),
            "token_estimate": token_estimate,
            "est_cost_usd":   round(cost, 6),
        })

        for issue in raw_issues:
            issue["file_path"] = chunk.file_path
            issue["line"]      = int(issue.get("line", chunk.start_line))

        metrics.record_file(
            chunk.file_path,
            raw_issues=len(raw_issues),
            kept_issues=0,   # updated after filtering
            token_estimate=token_estimate,
        )
        all_issues.extend(raw_issues)

    log.info("Filtering issues", extra={"raw_total": len(all_issues)})
    kept = filter_issues(all_issues)
    log.info("Issues after confidence filter", extra={"kept": len(kept)})

    # Deduplicate against what's already on the PR
    new_issues = deduplicate(kept, existing_fingerprints)
    log.info("New issues to post", extra={"count": len(new_issues)})

    posted = 0
    for issue in new_issues:
        body = format_comment(issue)
        success = gh.post_review_comment(
            commit_sha=commit_sha,
            path=issue["file_path"],
            line=issue["line"],
            body=body,
        )
        if not success:
            log.warning("Inline comment rejected, falling back to PR comment", extra={
                "file_path": issue["file_path"],
                "line":      issue["line"],
            })
            gh.post_pr_comment(body)
        posted += 1

    summary = build_summary(kept, files_reviewed, skipped)
    gh.post_pr_comment(summary)

    metrics.finalize(
        issues_kept_total=len(kept),
        files_reviewed=files_reviewed,
        files_skipped=skipped,
        estimated_cost_usd=total_estimated_cost,
    )
    metrics.save("review_metrics.json")

    log.info("Reviewer finished", extra={
        "files_reviewed":      files_reviewed,
        "files_skipped":       skipped,
        "issues_raw":          len(all_issues),
        "issues_kept":         len(kept),
        "issues_posted":       posted,
        "issues_deduplicated": len(kept) - len(new_issues),
        "estimated_cost_usd":  round(total_estimated_cost, 6),
    })


if __name__ == "__main__":
    main()
