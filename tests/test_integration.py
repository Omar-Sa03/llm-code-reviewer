"""
Test suite for the LLM Code Reviewer.

All external HTTP calls (GitHub API + HuggingFace / OpenAI) are mocked so
the entire suite runs without credentials or network access.

Usage:
    python -m pytest tests/ -v
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from reviewer.diff_parser import DiffChunk, parse_diff, should_skip
from reviewer.confidence_filter import filter_issues
from reviewer.prompt import build_summary, SYSTEM_PROMPT
from reviewer.llm_client import _parse_json_response
from reviewer.deduplicator import deduplicate, fingerprint_issue
from reviewer.cost_estimator import estimate_cost
from reviewer.retry import retry_with_backoff, RetryExhausted
from reviewer.metrics import Metrics


# ── Sample data ──────────────────────────────────────────────────────────────

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

FAKE_ISSUE = {
    "line": 12,
    "severity": "error",
    "category": "security",
    "comment": "SQL injection vulnerability — use parameterised queries.",
    "confidence": 0.95,
    "file_path": "app/auth.py",
}

FAKE_LLM_RESPONSE = json.dumps([{
    "line": 12,
    "severity": "error",
    "category": "security",
    "comment": "SQL injection vulnerability — use parameterised queries.",
    "confidence": 0.95,
}])


# ── Diff parser ───────────────────────────────────────────────────────────────

def test_parse_diff_returns_chunks():
    chunks = list(parse_diff(SAMPLE_DIFF))
    assert len(chunks) == 1
    assert chunks[0].file_path == "app/auth.py"
    assert chunks[0].start_line == 10


def test_should_skip_lock_files():
    assert should_skip("package-lock.json") is True
    assert should_skip("yarn.lock") is True


def test_should_skip_dist():
    assert should_skip("dist/bundle.js") is True


def test_should_skip_source_files():
    assert should_skip("app/auth.py") is False
    assert should_skip("src/main.ts") is False


# ── Prompt ────────────────────────────────────────────────────────────────────

def test_system_prompt_not_empty():
    assert len(SYSTEM_PROMPT) > 50


def test_build_summary_format():
    issues = [
        {"severity": "error",      "file_path": "x.py"},
        {"severity": "warning",    "file_path": "x.py"},
        {"severity": "suggestion", "file_path": "y.py"},
    ]
    summary = build_summary(issues, files_reviewed=3, skipped=1)
    assert "LLM Code Review" in summary
    assert "Files reviewed" in summary
    assert "x.py" in summary


# ── LLM response parser ───────────────────────────────────────────────────────

def test_parse_valid_json():
    issues = _parse_json_response(FAKE_LLM_RESPONSE)
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert issues[0]["category"] == "security"


def test_parse_json_with_markdown_fences():
    wrapped = f"```json\n{FAKE_LLM_RESPONSE}\n```"
    issues = _parse_json_response(wrapped)
    assert len(issues) == 1


def test_parse_empty_array():
    assert _parse_json_response("[]") == []


def test_parse_garbage_returns_empty():
    assert _parse_json_response("not json at all") == []


def test_parse_json_with_reasoning_prefix():
    """v2 prompt may include chain-of-thought text before the array."""
    text = f"After analysis, here are the issues:\n\n{FAKE_LLM_RESPONSE}"
    issues = _parse_json_response(text)
    assert len(issues) == 1


def test_confidence_is_clamped():
    raw = json.dumps([{
        "line": 1, "severity": "error", "category": "bug",
        "comment": "x", "confidence": 1.5
    }])
    issues = _parse_json_response(raw)
    assert issues[0]["confidence"] == 1.0


def test_confidence_clamped_negative():
    raw = json.dumps([{
        "line": 1, "severity": "error", "category": "bug",
        "comment": "x", "confidence": -0.3
    }])
    issues = _parse_json_response(raw)
    assert issues[0]["confidence"] == 0.0


def test_missing_required_key_skipped():
    raw = json.dumps([{
        "line": 1, "severity": "error", "category": "bug",
        # "comment" and "confidence" are missing
    }])
    issues = _parse_json_response(raw)
    assert issues == []


# ── Confidence filter ─────────────────────────────────────────────────────────

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


def test_filter_sorts_by_severity():
    issues = [
        {"severity": "suggestion", "confidence": 0.92, "file_path": "a.py"},
        {"severity": "error",      "confidence": 0.90, "file_path": "b.py"},
        {"severity": "warning",    "confidence": 0.90, "file_path": "c.py"},
    ]
    kept = filter_issues(issues)
    assert kept[0]["severity"] == "error"
    assert kept[1]["severity"] == "warning"


# ── Deduplicator ──────────────────────────────────────────────────────────────

def test_deduplicate_removes_existing():
    issue = dict(FAKE_ISSUE)
    fp = fingerprint_issue(issue)
    result = deduplicate([issue], existing_fingerprints={fp})
    assert result == []


def test_deduplicate_keeps_new():
    issue = dict(FAKE_ISSUE)
    result = deduplicate([issue], existing_fingerprints=set())
    assert len(result) == 1


def test_deduplicate_mixed():
    issue1 = dict(FAKE_ISSUE)
    issue2 = {**FAKE_ISSUE, "line": 99, "comment": "Different issue entirely."}
    fp1 = fingerprint_issue(issue1)
    result = deduplicate([issue1, issue2], existing_fingerprints={fp1})
    assert len(result) == 1
    assert result[0]["line"] == 99


# ── Cost estimator ────────────────────────────────────────────────────────────

def test_cost_free_tier_is_zero():
    cost = estimate_cost("Qwen/Qwen2.5-Coder-32B-Instruct", input_tokens=1000)
    assert cost == 0.0


def test_cost_openai_model():
    cost = estimate_cost("gpt-4o-mini", input_tokens=1000, output_tokens=256)
    assert cost > 0.0


def test_cost_scales_with_tokens():
    small = estimate_cost("gpt-4o-mini", input_tokens=500)
    large = estimate_cost("gpt-4o-mini", input_tokens=5000)
    assert large > small


# ── Retry utility ─────────────────────────────────────────────────────────────

def test_retry_succeeds_on_first_attempt():
    calls = []
    def fn():
        calls.append(1)
        return "ok"
    result = retry_with_backoff(fn, retries=3, base_delay=0)
    assert result == "ok"
    assert len(calls) == 1


def test_retry_retries_on_failure():
    calls = []
    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("transient")
        return "recovered"
    result = retry_with_backoff(fn, retries=3, base_delay=0, retriable_exceptions=(TimeoutError,))
    assert result == "recovered"
    assert len(calls) == 3


def test_retry_raises_after_exhaustion():
    def fn():
        raise TimeoutError("always fails")
    with pytest.raises(RetryExhausted):
        retry_with_backoff(fn, retries=2, base_delay=0, retriable_exceptions=(TimeoutError,))


def test_retry_non_retriable_raises_immediately():
    calls = []
    def fn():
        calls.append(1)
        raise ValueError("non-retriable")
    with pytest.raises(ValueError):
        retry_with_backoff(fn, retries=3, base_delay=0, retriable_exceptions=(TimeoutError,))
    assert len(calls) == 1   # did not retry


# ── Metrics ───────────────────────────────────────────────────────────────────

def test_metrics_save(tmp_path):
    m = Metrics(run_id="test123", model="test-model")
    m.record_file("a.py", raw_issues=3, kept_issues=2, token_estimate=100)
    m.finalize(issues_kept_total=2, files_reviewed=1, files_skipped=0)
    out = tmp_path / "metrics.json"
    m.save(out)
    data = json.loads(out.read_text())
    assert data["run_id"] == "test123"
    assert data["summary"]["files_reviewed"] == 1
    assert data["summary"]["total_token_estimate"] == 100


# ── End-to-end pipeline (all HTTP mocked) ─────────────────────────────────────

@patch.dict(os.environ, {
    "GITHUB_TOKEN":        "fake-gh-token",
    "GITHUB_REPOSITORY":   "owner/repo",
    "PR_NUMBER":           "42",
    "PR_SHA":              "abc123",
    "HF_TOKEN":            "fake-hf-token",
    "LLM_PROVIDER":        "huggingface",
    "MODEL_NAME":          "Qwen/Qwen2.5-Coder-32B-Instruct",
    "PROMPT_VERSION":      "v2",
    "MAX_COMMENTS_TOTAL":  "8",
    "MAX_COMMENTS_PER_FILE": "3",
})
def test_full_pipeline():
    """Run main() end-to-end with all HTTP mocked — no real API calls."""

    # ── Mock the OpenAI client used by llm_client ──────────────────────────
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = FAKE_LLM_RESPONSE

    mock_openai_instance = MagicMock()
    mock_openai_instance.chat.completions.create.return_value = mock_completion

    # ── Mock GitHub HTTP responses ─────────────────────────────────────────
    diff_response = MagicMock()
    diff_response.status_code = 200
    diff_response.text = SAMPLE_DIFF
    diff_response.raise_for_status = MagicMock()

    existing_comments_response = MagicMock()
    existing_comments_response.status_code = 200
    existing_comments_response.json.return_value = []   # no existing comments
    existing_comments_response.raise_for_status = MagicMock()

    pr_meta_response = MagicMock()
    pr_meta_response.status_code = 200
    pr_meta_response.json.return_value = {"head": {"sha": "abc123"}}
    pr_meta_response.raise_for_status = MagicMock()

    comment_response = MagicMock()
    comment_response.status_code = 201
    comment_response.raise_for_status = MagicMock()

    def gh_get_side_effect(url, **kwargs):
        accept = kwargs.get("headers", {}).get("Accept", "")
        if "diff" in accept:
            return diff_response
        if "comments" in url:
            return existing_comments_response
        return pr_meta_response

    with patch("reviewer.llm_client.OpenAI", return_value=mock_openai_instance), \
         patch("reviewer.github_client.requests.Session") as mock_session_cls:

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.headers = {}
        mock_session.mount = MagicMock()
        mock_session.get.side_effect = gh_get_side_effect
        mock_session.post.return_value = comment_response

        from reviewer.main import main
        main()   # should not raise

    # The summary comment + at least one inline comment should have been posted
    assert mock_session.post.call_count >= 1
