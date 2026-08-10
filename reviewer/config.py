"""
Central configuration for the LLM Code Reviewer.

All env-var reads are consolidated here so they can be validated once at
startup and injected in tests without patching os.environ everywhere.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field


@dataclass
class Config:
    # GitHub context
    github_token: str
    github_repository: str
    pr_number: int
    pr_sha: str

    # LLM settings
    hf_token: str
    model_name: str
    provider: str  # "huggingface" | "openai" | "anthropic"

    # Reviewer limits
    max_comments_total: int
    max_comments_per_file: int

    # Reliability settings
    llm_timeout_s: float
    llm_max_retries: int
    max_diff_tokens: int          # skip chunks larger than this estimate
    fallback_model: str           # e.g. "gpt-4o-mini" — empty string = no fallback

    # Cost guard
    cost_limit_usd: float         # warn / skip when estimated cost exceeds this

    # Observability
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    prompt_version: str = "v2"


def load_config() -> Config:
    """Load and validate configuration from environment variables."""

    def _require(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise OSError(
                f"Required environment variable '{name}' is not set or empty."
            )
        return value

    def _optional(name: str, default: str = "") -> str:
        return os.environ.get(name, default).strip()

    def _int(name: str, default: int) -> int:
        raw = os.environ.get(name, str(default))
        try:
            return int(raw)
        except ValueError:
            raise OSError(
                f"Environment variable '{name}' must be an integer, got: {raw!r}"
            )

    def _float(name: str, default: float) -> float:
        raw = os.environ.get(name, str(default))
        try:
            return float(raw)
        except ValueError:
            raise OSError(
                f"Environment variable '{name}' must be a float, got: {raw!r}"
            )

    pr_sha = _optional("PR_SHA")

    return Config(
        github_token=_require("GITHUB_TOKEN"),
        github_repository=_require("GITHUB_REPOSITORY"),
        pr_number=_int("PR_NUMBER", 0),
        pr_sha=pr_sha,
        hf_token=_optional("HF_TOKEN"),
        model_name=_optional("MODEL_NAME", "Qwen/Qwen2.5-Coder-32B-Instruct"),
        provider=_optional("LLM_PROVIDER", "huggingface"),
        max_comments_total=_int("MAX_COMMENTS_TOTAL", 8),
        max_comments_per_file=_int("MAX_COMMENTS_PER_FILE", 3),
        llm_timeout_s=_float("LLM_TIMEOUT_S", 30.0),
        llm_max_retries=_int("LLM_MAX_RETRIES", 3),
        max_diff_tokens=_int("MAX_DIFF_TOKENS", 6000),
        fallback_model=_optional("FALLBACK_MODEL", ""),
        cost_limit_usd=_float("COST_LIMIT_USD", 0.10),
        prompt_version=_optional("PROMPT_VERSION", "v2"),
    )
