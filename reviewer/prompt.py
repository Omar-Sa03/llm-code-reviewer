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

    total = len(issues)

    # One-line summary
    if total == 0:
        headline = "No issues found — looks good! ✅"
    else:
        parts = []
        if errors:
            parts.append(f"{errors} error{'s' if errors != 1 else ''}")
        if warnings:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
        if suggestions:
            parts.append(f"{suggestions} suggestion{'s' if suggestions != 1 else ''}")
        headline = f"Found {', '.join(parts)} across {len(by_file)} file{'s' if len(by_file) != 1 else ''}."

    # Per-file breakdown (only if there are issues)
    file_section = ""
    if by_file:
        file_lines = "\n".join(
            f"- `{path}` — {len(fi)} issue{'s' if len(fi) != 1 else ''}"
            for path, fi in sorted(by_file.items())
        )
        file_section = f"\n\n{file_lines}"

    return f"""### Code Review Summary

{headline}

Reviewed **{files_reviewed}** file{'s' if files_reviewed != 1 else ''}{f', skipped {skipped}' if skipped else ''}.{file_section}
"""