"""Token usage to dollars, using the editable table in prices.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @classmethod
    def from_converse(cls, usage: dict | None) -> "Usage":
        usage = usage or {}
        return cls(
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            cache_read_tokens=int(usage.get("cacheReadInputTokens", 0) or 0),
            cache_write_tokens=int(usage.get("cacheWriteInputTokens", 0) or 0),
        )

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )

    def as_dict(self) -> dict:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cacheReadTokens": self.cache_read_tokens,
            "cacheWriteTokens": self.cache_write_tokens,
        }


@lru_cache(maxsize=1)
def _prices() -> dict:
    data = json.loads((Path(__file__).parent / "prices.json").read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def price_for(model_id: str) -> dict | None:
    # Longest matching key wins, so "nova-lite" never matches a "nova-pro" ID.
    matches = [k for k in _prices() if k in model_id]
    return _prices()[max(matches, key=len)] if matches else None


def cost_usd(model_id: str, usage: Usage) -> float | None:
    """Approximate on-demand cost. Cache reads are billed at a discount that varies
    by model; we conservatively bill them at the full input rate. Returns None if
    the model has no price entry."""
    p = price_for(model_id)
    if p is None:
        return None
    billed_input = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    return billed_input / 1000 * p["input_per_1k"] + usage.output_tokens / 1000 * p["output_per_1k"]
