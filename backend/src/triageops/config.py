"""Runtime configuration, read from environment variables set by the CDK stack."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    region: str
    table_name: str
    raw_bucket: str
    queue_url: str
    state_machine_arn: str
    guardrail_id: str
    guardrail_version: str
    classify_model_id: str
    draft_model_id: str
    embed_model_id: str
    vector_bucket: str
    ticket_index: str
    kb_id: str
    confidence_threshold: float
    duplicate_threshold: float
    prompt_cache: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        region=env("AWS_REGION", env("AWS_DEFAULT_REGION", "us-east-1")),
        table_name=env("TABLE_NAME", ""),
        raw_bucket=env("RAW_BUCKET", ""),
        queue_url=env("QUEUE_URL", ""),
        state_machine_arn=env("STATE_MACHINE_ARN", ""),
        guardrail_id=env("GUARDRAIL_ID", ""),
        guardrail_version=env("GUARDRAIL_VERSION", "DRAFT"),
        classify_model_id=env("CLASSIFY_MODEL_ID", "us.amazon.nova-lite-v1:0"),
        draft_model_id=env("DRAFT_MODEL_ID", "us.amazon.nova-pro-v1:0"),
        embed_model_id=env("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"),
        vector_bucket=env("VECTOR_BUCKET", ""),
        ticket_index=env("TICKET_INDEX", ""),
        kb_id=env("KB_ID", ""),
        confidence_threshold=_float("CONFIDENCE_THRESHOLD", 0.7),
        duplicate_threshold=_float("DUPLICATE_THRESHOLD", 0.85),
        prompt_cache=env("PROMPT_CACHE", "false").lower() == "true",
    )
