"""
LLM client with retry, provider fallback, token budget guard, and typed errors.

Supports three providers, selected via the ``provider`` field on Config:
  - ``huggingface``  HuggingFace Inference Routing (default, free tier)
  - ``openai``       OpenAI API (needs OPENAI_API_KEY)
  - ``anthropic``    Anthropic API (needs ANTHROPIC_API_KEY) — uses openai-compat endpoint

Error handling:
  - Transient errors (5xx, timeout, rate-limit) are retried with exponential backoff.
  - Non-retriable errors raise immediately.
  - After all retries are exhausted, the function returns [] so the pipeline
    can continue reviewing other files rather than failing the whole run.
"""
from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING

from openai import (
    APIConnectionError,
    APIStatusError,
    OpenAI,
    RateLimitError,
)

from reviewer.logger import get_logger
from reviewer.prompts import get_prompt
from reviewer.retry import RetryExhausted, retry_with_backoff

if TYPE_CHECKING:
    from reviewer.config import Config

log = get_logger(__name__)

# ── Provider base URLs ─────────────────────────────────────────────────────
_PROVIDER_URLS = {
    "huggingface": "https://router.huggingface.co/v1",
    "openai":      "https://api.openai.com/v1",
    # Anthropic via their OpenAI-compatible endpoint
    "anthropic":   "https://api.anthropic.com/v1",
    # Groq: free tier, fast, no credit card needed — https://console.groq.com/
    "groq":        "https://api.groq.com/openai/v1",
    # OpenRouter: free models available — https://openrouter.ai/
    "openrouter":  "https://openrouter.ai/api/v1",
}

# ── Retriable HTTP status codes ────────────────────────────────────────────
_RETRIABLE_STATUS = {429, 500, 502, 503, 504}

# ── Rough token estimator (chars ÷ 4 is a common heuristic for English) ───
def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _make_client(provider: str, api_key: str, timeout: float = 30.0) -> OpenAI:
    base_url = _PROVIDER_URLS.get(provider)
    if not base_url:
        raise ValueError(f"Unknown provider: {provider!r}. Choose from {list(_PROVIDER_URLS)}")
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)


def _resolve_api_key(provider: str, cfg: "Config") -> str:
    """Return the correct API key for the chosen provider."""
    if provider == "huggingface":
        key = cfg.hf_token or os.environ.get("HF_TOKEN", "")
        if not key:
            raise EnvironmentError("HF_TOKEN is required for the huggingface provider.")
        return key
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise EnvironmentError("OPENAI_API_KEY is required for the openai provider.")
        return key
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise EnvironmentError("ANTHROPIC_API_KEY is required for the anthropic provider.")
        return key
    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise EnvironmentError(
                "GROQ_API_KEY is required for the groq provider. "
                "Get a free key at https://console.groq.com/"
            )
        return key
    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise EnvironmentError(
                "OPENROUTER_API_KEY is required for the openrouter provider. "
                "Get a free key at https://openrouter.ai/"
            )
        return key
    raise ValueError(f"Unknown provider: {provider!r}")


def _single_review_call(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """One attempt at an LLM call. Raises on any error."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=1024,
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


def _is_retriable(exc: Exception) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code in _RETRIABLE_STATUS:
        return True
    if isinstance(exc, APIConnectionError):
        return True
    return False


def review_chunk(diff_content: str, cfg: "Config") -> list[dict]:
    """
    Review a single diff chunk and return a list of issue dicts.

    - Enforces a token budget (skips oversized chunks to control cost).
    - Retries on transient failures with exponential backoff.
    - Falls back to an alternate model/provider if configured and primary fails.
    - Always returns a list (empty on unrecoverable error) so the pipeline continues.
    """
    system_prompt, build_prompt_fn = get_prompt(cfg.prompt_version)
    user_prompt = build_prompt_fn(diff_content)

    token_estimate = _estimate_tokens(system_prompt + user_prompt)
    if token_estimate > cfg.max_diff_tokens:
        log.warning(
            "Skipping oversized chunk",
            extra={"token_estimate": token_estimate, "limit": cfg.max_diff_tokens},
        )
        return []

    def attempt(provider: str, model: str) -> list[dict]:
        api_key = _resolve_api_key(provider, cfg)
        client  = _make_client(provider, api_key, timeout=cfg.llm_timeout_s)

        def _call() -> str:
            try:
                return _single_review_call(client, model, system_prompt, user_prompt)
            except APIStatusError as exc:
                # Billing / auth errors are permanent — retrying won't help
                if exc.status_code in {401, 402, 403}:
                    raise RuntimeError(
                        f"Non-retriable API error {exc.status_code}: {exc.message}"
                    ) from exc
                raise  # let retry_with_backoff handle transient 5xx / 429

        try:
            raw_text = retry_with_backoff(
                fn=_call,
                retries=cfg.llm_max_retries,
                base_delay=2.0,
                retriable_exceptions=(RateLimitError, APIStatusError, APIConnectionError, TimeoutError),
            )
            issues = _parse_json_response(raw_text.strip())
            log.info(
                "LLM call succeeded",
                extra={"provider": provider, "model": model,
                       "token_estimate": token_estimate, "raw_issues": len(issues)},
            )
            return issues
        except RetryExhausted as exc:
            log.error(
                "LLM call failed after retries",
                extra={"provider": provider, "model": model, "error": str(exc.last_error)},
            )
            raise

    # ── Primary attempt ────────────────────────────────────────────────────
    try:
        return attempt(cfg.provider, cfg.model_name)
    except (RetryExhausted, RuntimeError, EnvironmentError, ValueError) as primary_exc:
        log.error("Primary LLM call failed: %s", primary_exc)

        # ── Fallback attempt ───────────────────────────────────────────────
        if cfg.fallback_model:
            # Infer provider from model name heuristic
            fallback_provider = "openai" if cfg.fallback_model.startswith("gpt") else cfg.provider
            log.info(
                "Attempting fallback",
                extra={"fallback_model": cfg.fallback_model, "fallback_provider": fallback_provider},
            )
            try:
                return attempt(fallback_provider, cfg.fallback_model)
            except (RetryExhausted, RuntimeError, EnvironmentError, ValueError) as fallback_exc:
                log.error("Fallback LLM call also failed: %s", fallback_exc)

        return []


def _parse_json_response(text: str) -> list[dict]:
    """Extract and validate a JSON array from raw LLM output."""
    # Strip markdown fences if the model wraps output anyway
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()

    # Some models prefix with reasoning text before the array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        log.warning("No JSON array found in LLM response", extra={"preview": text[:200]})
        return []

    try:
        issues = json.loads(match.group())
        if not isinstance(issues, list):
            return []

        valid = []
        required_keys = {"line", "severity", "category", "comment", "confidence"}
        for issue in issues:
            if required_keys.issubset(issue.keys()):
                issue["confidence"] = max(0.0, min(1.0, float(issue["confidence"])))
                valid.append(issue)

        return valid

    except json.JSONDecodeError as exc:
        log.error(
            "JSON parse error in LLM response",
            extra={"error": str(exc), "preview": text[:200]},
        )
        return []