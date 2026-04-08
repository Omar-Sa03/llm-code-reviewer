from typing import Any

SEVERITY_THRESHOLDS = {
    "error":      0.70,
    "warning":    0.78,
    "suggestion": 0.88,
}

MAX_COMMENTS_PER_FILE = 3   
MAX_COMMENTS_TOTAL    = 8   


def filter_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    passed = [
        issue for issue in issues
        if issue["confidence"] >= SEVERITY_THRESHOLDS.get(issue["severity"], 0.85)
    ]

    priority = {"error": 0, "warning": 1, "suggestion": 2}
    passed.sort(key=lambda x: (priority.get(x["severity"], 3), -x["confidence"]))

    file_counts: dict[str, int] = {}
    capped = []
    for issue in passed:
        fp = issue["file_path"]
        if file_counts.get(fp, 0) < MAX_COMMENTS_PER_FILE:
            capped.append(issue)
            file_counts[fp] = file_counts.get(fp, 0) + 1

    return capped[:MAX_COMMENTS_TOTAL]