"""
Smoke‑test the full reviewer pipeline without hitting any external APIs.
Mocks the GitHub and Hugging Face endpoints so the entire flow can run locally.

Usage:
    python -m pytest tests/test_integration.py -v
"""

import json
import os
from unittest.mock import patch, MagicMock

from reviewer.diff_parser import parse_diff, should_skip
from reviewer.confidence_filter import filter_issues
from reviewer.prompt import build_prompt, build_summary, SYSTEM_PROMPT
from reviewer.llm_client import _parse_json_response


# ── Sample data ─────────────────────────────────────────────────────

SAMPLE_DIFF = """\
diff --git a/app/auth.py b/app/auth.py
index abc..def 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,6 +10,9 @@
 def existing_function():
     pass
+
+def login(user, password):
+    return db.query(f"SELECT * FROM users WHERE pass='{password}'")
"""

FAKE_LLM_RESPONSE = json.dumps([
    {
        "line": 3,
        "severity": "error",
        "category": "security",
        "comment": "SQL injection vulnerability – use parameterised queries.",
        "confidence": 0.95,
    }
])


# ── Diff parser tests ──────────────────────────────────────────────

def test_parse_diff_returns_chunks():
    chunks = list(parse_diff(SAMPLE_DIFF))
    assert len(chunks) == 1
    assert chunks[0].file_path == "app/auth.py"
    assert chunks[0].start_line == 10


def test_should_skip():
    assert should_skip("package-lock.json") is True
    assert should_skip("dist/bundle.js") is True
    assert should_skip("app/auth.py") is False


# ── Prompt tests ───────────────────────────────────────────────────

def test_system_prompt_not_empty():
    assert len(SYSTEM_PROMPT) > 50


def test_build_prompt_includes_diff():
    prompt = build_prompt("+ new line")
    assert "+ new line" in prompt


# ── LLM response parser tests ─────────────────────────────────────

def test_parse_valid_json():
    issues = _parse_json_response(FAKE_LLM_RESPONSE)
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"


def test_parse_json_with_markdown_fences():
    wrapped = f"```json\n{FAKE_LLM_RESPONSE}\n```"
    issues = _parse_json_response(wrapped)
    assert len(issues) == 1


def test_parse_empty_array():
    assert _parse_json_response("[]") == []


def test_parse_garbage():
    assert _parse_json_response("not json at all") == []


def test_confidence_is_clamped():
    raw = json.dumps([{
        "line": 1, "severity": "error", "category": "bug",
        "comment": "x", "confidence": 1.5
    }])
    issues = _parse_json_response(raw)
    assert issues[0]["confidence"] == 1.0


# ── Confidence filter tests ───────────────────────────────────────

def test_filter_removes_low_confidence():
    issues = [
        {"severity": "error",   "confidence": 0.95, "file_path": "a.py"},
        {"severity": "error",   "confidence": 0.30, "file_path": "a.py"},  # below 0.70
        {"severity": "warning", "confidence": 0.50, "file_path": "b.py"},  # below 0.78
    ]
    kept = filter_issues(issues)
    assert len(kept) == 1
    assert kept[0]["confidence"] == 0.95


def test_filter_caps_per_file():
    issues = [
        {"severity": "error", "confidence": 0.95, "file_path": "a.py"},
        {"severity": "error", "confidence": 0.93, "file_path": "a.py"},
        {"severity": "error", "confidence": 0.91, "file_path": "a.py"},
        {"severity": "error", "confidence": 0.90, "file_path": "a.py"},  # 4th → capped
    ]
    kept = filter_issues(issues)
    assert len(kept) == 3  # MAX_COMMENTS_PER_FILE = 3


# ── Summary builder tests ─────────────────────────────────────────

def test_build_summary_format():
    issues = [
        {"severity": "error", "file_path": "x.py"},
        {"severity": "warning", "file_path": "x.py"},
    ]
    summary = build_summary(issues, files_reviewed=3, skipped=1)
    assert "LLM Code Review" in summary
    assert "Files reviewed" in summary


# ── End‑to‑end pipeline (mocked APIs) ─────────────────────────────

@patch.dict(os.environ, {
    "GITHUB_TOKEN": "fake-gh-token",
    "GITHUB_REPOSITORY": "owner/repo",
    "PR_NUMBER": "42",
    "PR_SHA": "abc123",
    "HF_TOKEN": "fake-hf-token",
})
@patch("reviewer.llm_client.requests")
@patch("reviewer.github_client.requests")
def test_full_pipeline(mock_gh_requests, mock_hf_requests):
    """Run the full main() with mocked HTTP — no real API calls."""

    # Mock GitHub GET (diff)
    diff_response = MagicMock()
    diff_response.status_code = 200
    diff_response.text = SAMPLE_DIFF
    diff_response.raise_for_status = MagicMock()
    mock_gh_requests.get.return_value = diff_response

    # Mock GitHub POST (review comments + summary)
    comment_response = MagicMock()
    comment_response.status_code = 201
    comment_response.raise_for_status = MagicMock()
    mock_gh_requests.post.return_value = comment_response

    # Mock Hugging Face POST (LLM inference)
    hf_response = MagicMock()
    hf_response.status_code = 200
    hf_response.json.return_value = [{"generated_text": FAKE_LLM_RESPONSE}]
    hf_response.raise_for_status = MagicMock()
    mock_hf_requests.post.return_value = hf_response

    from reviewer.main import main
    main()  # Should not raise

    # Verify GitHub received at least the summary comment
    assert mock_gh_requests.post.call_count >= 1
