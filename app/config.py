"""Centralized configuration, model naming, pricing, and system parameters for Nova DAW."""

import os
from typing import Dict, Tuple

# Default Models
DEFAULT_EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "gemini-3.8-flash")
DEFAULT_FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gemini-2.5-flash")
DEFAULT_ROUTER_MODEL = os.getenv("ROUTER_MODEL", "gemini-3.5-flash-lite")
DEFAULT_QUERY_MODEL = os.getenv("QUERY_MODEL", "gemini-3.5-flash-lite")

# Model Pricing Table (USD per 1,000,000 tokens)
# Note: Gemini 3.8 Flash rates are $0.75 prompt / $3.75 completion through Dec 31, 2026.
# Pricing table centralized to avoid stale hardcoded values across services.
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gemini-3.8-flash": {
        "prompt": 0.75,
        "completion": 3.75,
    },
    "gemini-2.5-flash": {
        "prompt": 0.15,
        "completion": 0.60,
    },
    "gemini-3.5-flash-lite": {
        "prompt": 0.075,
        "completion": 0.30,
    },
    "gemini-2.5-flash-lite": {
        "prompt": 0.075,
        "completion": 0.30,
    },
}

DEFAULT_PROMPT_PRICE = 0.75
DEFAULT_COMPLETION_PRICE = 3.75


def get_model_pricing(model_name: str) -> Tuple[float, float]:
    """Return (prompt_cost_per_million, completion_cost_per_million) for a model."""
    pricing = MODEL_PRICING.get(model_name)
    if pricing:
        return pricing["prompt"], pricing["completion"]
    return DEFAULT_PROMPT_PRICE, DEFAULT_COMPLETION_PRICE


def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate USD cost given model name, prompt tokens, and completion/thinking tokens."""
    prompt_rate, completion_rate = get_model_pricing(model_name)
    return round(
        (prompt_tokens / 1_000_000 * prompt_rate)
        + (completion_tokens / 1_000_000 * completion_rate),
        6,
    )


# Operational Parameters
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60.0"))
MIN_CONFIDENCE_AUTO_APPROVE = 0.85
NOVA_REQUIRE_DURABLE_STATE = os.getenv("NOVA_REQUIRE_DURABLE_STATE", "0").lower() in ("1", "true")
