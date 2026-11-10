"""Cached boto3 clients with adaptive retries.

Clients are created once per Lambda container and reused across invocations.
Adaptive retry mode backs off automatically when Bedrock throttles.
"""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from .config import get_settings

_RETRY = Config(retries={"max_attempts": 6, "mode": "adaptive"}, connect_timeout=5, read_timeout=60)


@lru_cache(maxsize=None)
def client(service: str):
    return boto3.client(service, region_name=get_settings().region, config=_RETRY)


@lru_cache(maxsize=None)
def table():
    return boto3.resource("dynamodb", region_name=get_settings().region).Table(get_settings().table_name)
