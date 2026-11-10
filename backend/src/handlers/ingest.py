"""POST /tickets (web form, Cognito auth) and POST /webhooks/alerts (API key).

Validates the payload, stores the raw text in the encrypted raw bucket, creates
the ticket row exactly once, and enqueues it. Returns 202 immediately: triage
happens asynchronously so an alert storm never times out the caller.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid

from pydantic import ValidationError

from triageops import storage
from triageops.aws import client, table
from triageops.config import get_settings
from triageops.http import error, header, json_body, response
from triageops.metrics import emit
from triageops.models import AlertIn, TicketIn

log = logging.getLogger()
log.setLevel(logging.INFO)


def make_ticket_id(ticket: TicketIn, idempotency_key: str | None) -> str:
    """Deterministic IDs for anything that can be retried, random IDs otherwise."""
    key = ticket.external_id or idempotency_key
    if key:
        return "T" + hashlib.sha256(f"{ticket.source}:{key}".encode()).hexdigest()[:19]
    return "T" + uuid.uuid4().hex[:19]


def parse(event: dict) -> TicketIn:
    body = json_body(event)
    if event.get("resource", "").startswith("/webhooks"):
        return AlertIn.model_validate(body).to_ticket()
    return TicketIn.model_validate(body)


def create_ticket(ticket: TicketIn, ticket_id: str, settings=None, s3=None, sqs=None, tbl=None) -> bool:
    settings = settings or get_settings()
    s3 = s3 or client("s3")
    sqs = sqs or client("sqs")
    tbl = tbl or table()

    raw_key = f"raw/{ticket_id}.json"
    created_at = storage.now_iso()
    s3.put_object(
        Bucket=settings.raw_bucket,
        Key=raw_key,
        Body=json.dumps(ticket.model_dump(mode="json")).encode(),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )
    created = storage.put_new_ticket(tbl, {
        "ticketId": ticket_id,
        "status": storage.STATUS_QUEUED,
        "source": ticket.source,
        "createdAt": created_at,
        "updatedAt": created_at,
        "rawKey": raw_key,
        "title": "(processing)",
    })
    if created:
        sqs.send_message(QueueUrl=settings.queue_url, MessageBody=json.dumps({"ticketId": ticket_id}))
    return created


def handler(event, _context):
    try:
        ticket = parse(event)
    except ValidationError as exc:
        return error(400, "invalid ticket", exc.errors(include_url=False, include_context=False))
    except (ValueError, json.JSONDecodeError) as exc:
        return error(400, f"invalid JSON: {exc}")

    ticket_id = make_ticket_id(ticket, header(event, "Idempotency-Key"))
    created = create_ticket(ticket, ticket_id)
    emit({"TicketsReceived": (1, "Count")}, {"Source": ticket.source})
    log.info(json.dumps({"msg": "ticket received", "ticketId": ticket_id, "created": created}))
    if not created:
        return response(200, {"ticketId": ticket_id, "status": "exists"})
    return response(202, {"ticketId": ticket_id, "status": storage.STATUS_QUEUED})
