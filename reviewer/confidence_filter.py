from typing import Any

SEVERITY_THRESHOLD = {
    "error": 0.7,
    "warning": 0.8,
    "suggestion": 0.9
}

MAX_COMMENTS_PER_PR = 8

def filter_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = []
    for issue in issues:
        threshold = SEVERITY_THRESHOLD.get(issue.get("severity", 0.85))
        if issue["confidence"] >= threshold:
            filtered.append(issue)

    priority = {"error": 0, "warning": 1, "suggestion": 2}
    filtered.sort(key=lambda x: (priority[x["severity"]], -x["confidence"]))
    return filtered[:MAX_COMMENTS_PER_PR]