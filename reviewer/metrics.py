"""
In-memory metrics collector for a single reviewer run.

Accumulates per-file and aggregate stats, then writes a structured
``review_metrics.json`` artifact that GitHub Actions uploads for later
querying via the GitHub API or local analysis.

Usage:
    from reviewer.metrics import Metrics

    m = Metrics(run_id="a1b2c3d4", model="Qwen/Qwen2.5-Coder-32B-Instruct")
    with m.time_llm_call("app/auth.py"):
        issues = review_chunk(content)
    m.record_file("app/auth.py", raw_issues=5, kept_issues=2, token_estimate=420)
    m.finalize(issues_total_kept=3, files_reviewed=4, files_skipped=1)
    m.save("review_metrics.json")
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator


@dataclass
class FileMetrics:
    file_path: str
    token_estimate: int = 0
    raw_issues: int = 0
    kept_issues: int = 0
    llm_duration_ms: float = 0.0
    llm_errors: int = 0


@dataclass
class Metrics:
    run_id: str
    model: str
    provider: str = "huggingface"
    prompt_version: str = "v2"

    _files: dict[str, FileMetrics] = field(default_factory=dict, repr=False)
    _run_start: float = field(default_factory=time.time, repr=False)

    # Aggregate — filled by finalize()
    total_duration_ms: float = 0.0
    files_reviewed: int = 0
    files_skipped: int = 0
    issues_raw_total: int = 0
    issues_kept_total: int = 0
    llm_errors_total: int = 0
    total_token_estimate: int = 0
    estimated_cost_usd: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @contextmanager
    def time_llm_call(self, file_path: str) -> Generator[None, None, None]:
        """Context manager that times an LLM call and records it against a file."""
        fm = self._files.setdefault(file_path, FileMetrics(file_path=file_path))
        start = time.time()
        try:
            yield
        except Exception:
            fm.llm_errors += 1
            raise
        finally:
            fm.llm_duration_ms += (time.time() - start) * 1000

    def record_file(
        self,
        file_path: str,
        raw_issues: int,
        kept_issues: int,
        token_estimate: int,
    ) -> None:
        fm = self._files.setdefault(file_path, FileMetrics(file_path=file_path))
        fm.raw_issues = raw_issues
        fm.kept_issues = kept_issues
        fm.token_estimate = token_estimate

    def record_llm_error(self, file_path: str) -> None:
        fm = self._files.setdefault(file_path, FileMetrics(file_path=file_path))
        fm.llm_errors += 1

    def finalize(
        self,
        issues_kept_total: int,
        files_reviewed: int,
        files_skipped: int,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        self.total_duration_ms = (time.time() - self._run_start) * 1000
        self.files_reviewed = files_reviewed
        self.files_skipped = files_skipped
        self.issues_kept_total = issues_kept_total
        self.issues_raw_total = sum(f.raw_issues for f in self._files.values())
        self.llm_errors_total = sum(f.llm_errors for f in self._files.values())
        self.total_token_estimate = sum(f.token_estimate for f in self._files.values())
        self.estimated_cost_usd = estimated_cost_usd

    def save(self, path: str | Path = "review_metrics.json") -> None:
        payload = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "model": self.model,
            "provider": self.provider,
            "prompt_version": self.prompt_version,
            "summary": {
                "files_reviewed": self.files_reviewed,
                "files_skipped": self.files_skipped,
                "issues_raw_total": self.issues_raw_total,
                "issues_kept_total": self.issues_kept_total,
                "llm_errors_total": self.llm_errors_total,
                "total_token_estimate": self.total_token_estimate,
                "estimated_cost_usd": round(self.estimated_cost_usd, 6),
                "total_duration_ms": round(self.total_duration_ms, 1),
            },
            "per_file": [
                {
                    "file_path": f.file_path,
                    "token_estimate": f.token_estimate,
                    "raw_issues": f.raw_issues,
                    "kept_issues": f.kept_issues,
                    "llm_duration_ms": round(f.llm_duration_ms, 1),
                    "llm_errors": f.llm_errors,
                }
                for f in self._files.values()
            ],
        }
        Path(path).write_text(json.dumps(payload, indent=2))
