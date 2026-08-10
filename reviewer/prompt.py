"""
Backward-compatibility shim.

New code should import from ``reviewer.prompts`` directly.
This module re-exports the active prompt (defaulting to v2) so existing
imports continue to work without changes.
"""
from reviewer.prompts.v2 import SYSTEM_PROMPT, build_prompt  # noqa: F401
from reviewer.prompts.v2 import PROMPT_VERSION               # noqa: F401


def build_summary(issues: list, files_reviewed: int, skipped: int) -> str:
    errors      = sum(1 for i in issues if i["severity"] == "error")
    warnings    = sum(1 for i in issues if i["severity"] == "warning")
    suggestions = len(issues) - errors - warnings

    by_file: dict[str, list] = {}
    for issue in issues:
        by_file.setdefault(issue["file_path"], []).append(issue)

    file_lines = "\n".join(
        f"| `{path}` | {len(file_issues)} |"
        for path, file_issues in sorted(by_file.items())
    ) or "| — | 0 |"

    return f"""## 🤖 LLM Code Review

**Files reviewed:** {files_reviewed} &nbsp;·&nbsp; **Skipped:** {skipped}

| Severity | Count |
|----------|-------|
| 🔴 Errors | {errors} |
| 🟡 Warnings | {warnings} |
| 🔵 Suggestions | {suggestions} |

### Issues by file
| File | Issues |
|------|--------|
{file_lines}

"""