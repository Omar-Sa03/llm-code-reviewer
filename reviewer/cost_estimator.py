"""
Per-model cost estimator.

Provides approximate USD cost per review chunk based on token estimates.
Costs are approximate and based on public pricing as of mid-2025.
Used for budget-guard logging and the ``estimated_cost_usd`` metric field.

For HuggingFace free-tier models the cost is $0 but the estimate is still
useful for understanding relative token consumption.
"""
from __future__ import annotations

# (input_cost_per_1k_tokens, output_cost_per_1k_tokens) in USD
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    # HuggingFace (free tier for most models — cost is API call overhead)
    "Qwen/Qwen2.5-Coder-32B-Instruct": (0.0, 0.0),
    "Qwen/Qwen2.5-Coder-7B-Instruct":  (0.0, 0.0),

    # OpenAI (May 2025 pricing)
    "gpt-4o":       (0.005,  0.015),
    "gpt-4o-mini":  (0.00015, 0.00060),
    "gpt-4-turbo":  (0.010,  0.030),
    "gpt-3.5-turbo":(0.0005, 0.0015),

    # Anthropic (May 2025 pricing)
    "claude-3-5-haiku-20241022":  (0.00080, 0.00400),
    "claude-3-5-sonnet-20241022": (0.00300, 0.01500),
    "claude-opus-4-5":            (0.01500, 0.07500),

    # Groq (free tier up to rate limits — great for evals)
    "llama-3.1-8b-instant":  (0.0, 0.0),
    "llama-3.3-70b-versatile": (0.0, 0.0),
    "qwen-qwq-32b":          (0.0, 0.0),

    # OpenRouter free models
    "meta-llama/llama-3.1-8b-instruct:free": (0.0, 0.0),
    "qwen/qwen-2.5-coder-7b-instruct:free":  (0.0, 0.0),
}

_DEFAULT_COST = (0.001, 0.002)   # conservative fallback for unknown models


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int = 256) -> float:
    """
    Estimate the USD cost of a single LLM call.

    Args:
        model_name:    Model identifier string (matched against known models).
        input_tokens:  Estimated input token count.
        output_tokens: Assumed output token count (default 256 — typical review response).

    Returns:
        Estimated cost in USD. Returns 0.0 for models with free-tier access.
    """
    # Fuzzy match: check if any known model name is a substring of the given name
    cost_entry = _DEFAULT_COST
    for known_model, costs in _MODEL_COSTS.items():
        if known_model.lower() in model_name.lower() or model_name.lower() in known_model.lower():
            cost_entry = costs
            break

    input_cost  = (input_tokens  / 1000) * cost_entry[0]
    output_cost = (output_tokens / 1000) * cost_entry[1]
    return input_cost + output_cost


def format_cost(usd: float) -> str:
    """Human-readable cost string."""
    if usd < 0.000001:
        return "$0.00 (free tier)"
    if usd < 0.001:
        return f"${usd * 1000:.4f}m"
    return f"${usd:.4f}"
