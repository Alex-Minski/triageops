"""DynamoDB access for the tickets table.

Table design (single table, on-demand):
  PK  ticketId
  GSI byStatus: PK status, SK createdAt  -> review queue and status filters

Raw ticket text (which can contain PII) is stored only in the encrypted raw S3
bucket with a short lifecycle; DynamoDB only ever holds the masked text.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

STATUS_QUEUED = "queued"
STATUS_TRIAGING = "triaging"
STATUS_TRIAGED = "triaged"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_REVIEWED = "reviewed"
STATUS_FAILED = "failed"
ALL_STATUSES = [STATUS_QUEUED, STATUS_TRIAGING, STATUS_TRIAGED, STATUS_NEEDS_REVIEW,
                STATUS_REVIEWED, STATUS_FAILED]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def to_ddb(value: Any) -> Any:
    """Floats are not allowed in DynamoDB; convert recursively to Decimal."""
    if value is None:
        return None
    return json.loads(json.dumps(value), parse_float=Decimal)


def from_ddb(value: Any) -> Any:
    if isinstance(value, list):
        return [from_ddb(v) for v in value]
    if isinstance(value, dict):
        return {k: from_ddb(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def put_new_ticket(table, item: dict) -> bool:
    """Insert a ticket once. Returns False if the ticketId already exists, which makes
    retried webhooks and at-least-once deliveries harmless."""
    try:
        table.put_item(Item=to_ddb(item), ConditionExpression="attribute_not_exists(ticketId)")
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def update(table, ticket_id: str, fields: dict) -> None:
    fields = {**fields, "updatedAt": now_iso()}
    names = {f"#{k}": k for k in fields}
    values = {f":{k}": v for k, v in to_ddb(fields).items()}
    table.update_item(
        Key={"ticketId": ticket_id},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ConditionExpression="attribute_exists(ticketId)",
    )


def get(table, ticket_id: str) -> dict | None:
    item = table.get_item(Key={"ticketId": ticket_id}).get("Item")
    return from_ddb(item) if item else None


def list_by_status(table, status: str, limit: int = 50, cursor: dict | None = None) -> tuple[list[dict], dict | None]:
    kwargs: dict = {
        "IndexName": "byStatus",
        "KeyConditionExpression": "#s = :s",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {":s": status},
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if cursor:
        kwargs["ExclusiveStartKey"] = cursor
    resp = table.query(**kwargs)
    return from_ddb(resp.get("Items", [])), resp.get("LastEvaluatedKey")


def scan_all(table, projection: list[str], max_items: int = 5000) -> list[dict]:
    """Full scan for the dashboard. Fine at portfolio scale (thousands of tickets);
    at real scale you would maintain aggregates with DynamoDB Streams instead."""
    names = {f"#{p}": p for p in projection}
    kwargs = {"ProjectionExpression": ", ".join(names), "ExpressionAttributeNames": names}
    items: list[dict] = []
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp or len(items) >= max_items:
            return from_ddb(items[:max_items])
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
