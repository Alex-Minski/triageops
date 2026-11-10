"""Small helpers for API Gateway proxy integrations."""

from __future__ import annotations

import base64
import json
from decimal import Decimal


def _default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(f"not serializable: {type(o)}")


def response(status: int, body: dict | list) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Api-Key,Idempotency-Key",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, default=_default),
    }


def error(status: int, message: str, details=None) -> dict:
    body = {"error": message}
    if details is not None:
        body["details"] = details
    return response(status, body)


def json_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data


def header(event: dict, name: str) -> str | None:
    for k, v in (event.get("headers") or {}).items():
        if k.lower() == name.lower():
            return v
    return None


def caller(event: dict) -> str:
    claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims") or {}
    return claims.get("email") or claims.get("cognito:username") or "unknown"
