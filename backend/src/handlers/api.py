"""Read and review API for the web app (all routes behind the Cognito authorizer).

  GET  /tickets?status=needs_review&limit=50&cursor=...
  GET  /tickets/{ticketId}
  POST /tickets/{ticketId}/review
  GET  /stats
"""

from __future__ import annotations

import base64
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from triageops import storage
from triageops.aws import table
from triageops.http import caller, error, json_body, response
from triageops.metrics import emit
from triageops.models import ReviewIn

log = logging.getLogger()
log.setLevel(logging.INFO)

LIST_FIELDS = ["ticketId", "status", "source", "title", "createdAt", "triage", "reviewReasons",
               "duplicateOf", "costUsd", "review"]


def _encode_cursor(key: dict | None) -> str | None:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode() if key else None


def _decode_cursor(raw: str | None) -> dict | None:
    return json.loads(base64.urlsafe_b64decode(raw.encode())) if raw else None


def list_tickets(event, tbl):
    q = event.get("queryStringParameters") or {}
    status = q.get("status", storage.STATUS_NEEDS_REVIEW)
    if status not in storage.ALL_STATUSES:
        return error(400, f"status must be one of {storage.ALL_STATUSES}")
    limit = max(1, min(int(q.get("limit", 50)), 100))
    items, last = storage.list_by_status(tbl, status, limit, _decode_cursor(q.get("cursor")))
    slim = [{k: it.get(k) for k in LIST_FIELDS if k in it} for it in items]
    return response(200, {"items": slim, "cursor": _encode_cursor(last)})


def get_ticket(ticket_id: str, tbl):
    item = storage.get(tbl, ticket_id)
    if not item:
        return error(404, "ticket not found")
    item.pop("rawKey", None)
    return response(200, item)


def review_ticket(event, ticket_id: str, tbl):
    try:
        review = ReviewIn.model_validate(json_body(event))
    except ValidationError as exc:
        return error(400, "invalid review", exc.errors(include_url=False, include_context=False))
    item = storage.get(tbl, ticket_id)
    if not item:
        return error(404, "ticket not found")
    triage = item.get("triage") or {}
    agreed = triage.get("category") == review.category.value and triage.get("priority") == review.priority.value
    storage.update(tbl, ticket_id, {
        "status": storage.STATUS_REVIEWED,
        "review": {**review.model_dump(mode="json"), "reviewer": caller(event),
                   "reviewedAt": storage.now_iso(), "agreedWithModel": agreed},
    })
    emit({"Reviews": (1, "Count"), "ReviewAgreed": (1 if agreed else 0, "Count")})
    return response(200, {"ticketId": ticket_id, "status": storage.STATUS_REVIEWED, "agreedWithModel": agreed})


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def compute_stats(items: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    by_status = Counter(i.get("status") for i in items)
    by_category: Counter = Counter()
    by_priority: Counter = Counter()
    costs, latencies = [], []
    reviewed, agreed = 0, 0
    clusters: dict[str, list[dict]] = defaultdict(list)
    titles = {i["ticketId"]: i.get("title", "") for i in items}
    daily: Counter = Counter()

    for i in items:
        final = i.get("review") or i.get("triage") or {}
        if final.get("category"):
            by_category[final["category"]] += 1
        if final.get("priority"):
            by_priority[final["priority"]] += 1
        if i.get("costUsd") is not None:
            costs.append(float(i["costUsd"]))
        if i.get("e2eLatencyMs") is not None:
            latencies.append(float(i["e2eLatencyMs"]))
        if i.get("review") and i.get("triage", {}).get("category"):
            reviewed += 1
            agreed += 1 if i["review"].get("agreedWithModel") else 0
        if i.get("duplicateOf"):
            clusters[i["duplicateOf"]].append(i)
        if i.get("createdAt"):
            day = i["createdAt"][:10]
            if day >= (now - timedelta(days=13)).date().isoformat():
                daily[day] += 1

    decided = by_status[storage.STATUS_TRIAGED] + by_status[storage.STATUS_NEEDS_REVIEW] + by_status[storage.STATUS_REVIEWED]
    top_clusters = sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True)[:5]
    days = [(now - timedelta(days=d)).date().isoformat() for d in range(13, -1, -1)]
    return {
        "total": len(items),
        "byStatus": dict(by_status),
        "byCategory": dict(by_category),
        "byPriority": dict(by_priority),
        "autoTriageRate": round(by_status[storage.STATUS_TRIAGED] / decided, 4) if decided else None,
        "reviewAgreementRate": round(agreed / reviewed, 4) if reviewed else None,
        "reviewedCount": reviewed,
        "costUsd": {
            "total": round(sum(costs), 6),
            "perTicket": round(sum(costs) / len(costs), 8) if costs else None,
            "per1000Tickets": round(sum(costs) / len(costs) * 1000, 4) if costs else None,
        },
        "latencyMs": {"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
        "recurring": [
            {"ticketId": root, "title": titles.get(root, ""), "duplicates": len(dups)}
            for root, dups in top_clusters
        ],
        "daily": [{"date": d, "count": daily.get(d, 0)} for d in days],
    }


def handler(event, _context, tbl=None):
    tbl = tbl or table()
    method, resource = event.get("httpMethod"), event.get("resource")
    ticket_id = (event.get("pathParameters") or {}).get("ticketId")
    try:
        if method == "GET" and resource == "/tickets":
            return list_tickets(event, tbl)
        if method == "GET" and resource == "/tickets/{ticketId}":
            return get_ticket(ticket_id, tbl)
        if method == "POST" and resource == "/tickets/{ticketId}/review":
            return review_ticket(event, ticket_id, tbl)
        if method == "GET" and resource == "/stats":
            fields = ["ticketId", "status", "title", "createdAt", "triage", "review",
                      "costUsd", "e2eLatencyMs", "duplicateOf"]
            return response(200, compute_stats(storage.scan_all(tbl, fields)))
        return error(404, "route not found")
    except (ValueError, json.JSONDecodeError) as exc:
        return error(400, str(exc))
