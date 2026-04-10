SYSTEM_PROMPT = """
You are a senior code reviewer. Analyze the provided code diff and return ONLY a JSON array.
The diff lines are prefixed with their actual line numbers.
Each item must have these exact keys:
- "line": integer (the line number provided at the START of the line in the diff)
- "severity": "error" | "warning" | "suggestion"
- "category": "security" | "bug" | "performance" | "style" | "logic"
- "comment": string
- "confidence": float between 0.0 and 1.0

Rules:
- Return [] if no issues are found
- Return ONLY the JSON array, no explanation, no markdown fences, no other text
- Only flag issues on added lines (starting with '+')
""".strip()


def build_prompt(diff_content: str) -> str:
    return f"""Review this code diff and return a JSON array of issues:

{diff_content}

Return ONLY the JSON array."""


def build_summary(issues: list, files_reviewed: int, skipped: int) -> str:
    errors      = sum(1 for i in issues if i["severity"] == "error")
    warnings    = sum(1 for i in issues if i["severity"] == "warning")
    suggestions = len(issues) - errors - warnings

    by_file = {}
    for issue in issues:
        by_file.setdefault(issue["file_path"], []).append(issue)

    file_lines = "\n".join(
        f"| `{path}` | {len(file_issues)} |"
        for path, file_issues in sorted(by_file.items())
    ) or "| — | 0 |"

    return f"""## LLM Code Review

· **Files reviewed:** {files_reviewed} · **Skipped:** {skipped}

| Severity | Count |
|----------|-------|
|  Errors | {errors} |
|  Warnings | {warnings} |
|  Suggestions | {suggestions} |

### Issues by file
| File | Issues |
|------|--------|
{file_lines}

"""