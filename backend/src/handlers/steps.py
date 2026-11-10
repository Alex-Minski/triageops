"""Step Functions task handlers, one function per workflow state.

State shape as it moves through the workflow:
  {"ticketId": ...}
  + "mask":           masked title/description, PII types, prompt-attack flag
  + "classification": triage decision, usage, cost, latency (or parseError)
  + "duplicates":     nearest past tickets and the duplicate decision
  + "draft":          runbook-grounded resolution with citations
Finalize writes everything to DynamoDB and decides whether a human must review.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from triageops import classifier, dedupe, drafter, guardrails, storage
from triageops.aws import client, table
from triageops.config import get_settings
from triageops.metrics import emit
from triageops.pricing import cost_usd

log = logging.getLogger()
log.setLevel(logging.INFO)


def mask_handler(event, _context):
    s = get_settings()
    ticket_id = event["ticketId"]
    item = storage.get(table(), ticket_id)
    raw = json.loads(client("s3").get_object(Bucket=s.raw_bucket, Key=item["rawKey"])["Body"].read())

    title = guardrails.apply(raw["title"], s.guardrail_id, s.guardrail_version)
    body = guardrails.apply(raw["description"], s.guardrail_id, s.guardrail_version)
    result = {
        "title": title.text,
        "description": body.text,
        "piiTypes": sorted(set(title.pii_types) | set(body.pii_types)),
        "promptAttack": title.prompt_attack or body.prompt_attack,
        "engine": body.engine,
    }
    storage.update(table(), ticket_id, {
        "status": storage.STATUS_TRIAGING,
        "title": result["title"],
        "description": result["description"],
        "piiTypes": result["piiTypes"],
        "promptAttack": result["promptAttack"],
    })
    return result


def classify_handler(event, _context):
    s = get_settings()
    m = event["mask"]
    try:
        res = classifier.classify(m["title"], m["description"], s.classify_model_id,
                                  prompt_cache=s.prompt_cache)
        return res.as_dict()
    except classifier.TriageParseError as exc:
        log.warning(json.dumps({"msg": "triage parse error", "ticketId": event["ticketId"], "error": str(exc)}))
        return {"parseError": str(exc)[:500], "modelId": s.classify_model_id}


def duplicates_handler(event, _context):
    s = get_settings()
    if not s.vector_bucket:
        return {"skipped": True, "neighbours": []}
    m = event["mask"]
    category = event["classification"].get("category", "unknown")
    vector, usage = dedupe.embed(f"{m['title']}\n{m['description']}", s.embed_model_id)
    neighbours = dedupe.find_similar(vector, s.vector_bucket, s.ticket_index, exclude_id=event["ticketId"])
    dedupe.store(event["ticketId"], vector, m["title"], category, storage.now_iso(),
                 s.vector_bucket, s.ticket_index)
    top = neighbours[0] if neighbours else None
    is_dup = bool(top and top.similarity >= s.duplicate_threshold)
    return {
        "neighbours": [n.as_dict() for n in neighbours],
        "isDuplicate": is_dup,
        "duplicateOf": top.ticket_id if is_dup else None,
        "embedTokens": usage.input_tokens,
        "embedCostUsd": cost_usd(s.embed_model_id, usage),
    }


def draft_handler(event, _context):
    s = get_settings()
    if not s.kb_id:
        return {"skipped": True}
    m = event["mask"]
    ticket_text = f"Title: {m['title']}\nDescription: {m['description']}"
    chunks = drafter.retrieve(ticket_text, s.kb_id)
    d = drafter.draft(ticket_text, event["classification"].get("category", "unknown"), chunks, s.draft_model_id)
    return d.as_dict()


def review_reasons(state: dict, threshold: float) -> list[str]:
    reasons = []
    cls = state.get("classification") or {}
    if "parseError" in cls:
        reasons.append("invalid_model_output")
    elif float(cls.get("confidence", 0)) < threshold:
        reasons.append("low_confidence")
    if (state.get("mask") or {}).get("promptAttack"):
        reasons.append("possible_prompt_injection")
    return reasons


def total_cost(state: dict) -> float:
    parts = [
        (state.get("classification") or {}).get("costUsd"),
        (state.get("duplicates") or {}).get("embedCostUsd"),
        (state.get("draft") or {}).get("costUsd"),
    ]
    return round(sum(p for p in parts if p), 8)


def finalize_handler(event, _context):
    s = get_settings()
    ticket_id = event["ticketId"]
    item = storage.get(table(), ticket_id)
    created = datetime.fromisoformat(item["createdAt"])
    e2e_ms = int((datetime.now(timezone.utc) - created).total_seconds() * 1000)

    reasons = review_reasons(event, s.confidence_threshold)
    status = storage.STATUS_NEEDS_REVIEW if reasons else storage.STATUS_TRIAGED
    cls = event.get("classification") or {}
    dup = event.get("duplicates") or {}
    cost = total_cost(event)

    storage.update(table(), ticket_id, {
        "status": status,
        "triage": cls,
        "duplicates": dup.get("neighbours", []),
        "duplicateOf": dup.get("duplicateOf"),
        "draft": event.get("draft") or {},
        "reviewReasons": reasons,
        "costUsd": cost,
        "e2eLatencyMs": e2e_ms,
        "triagedAt": storage.now_iso(),
    })
    emit({
        "TicketsTriaged": (1, "Count"),
        "NeedsReview": (1 if reasons else 0, "Count"),
        "DuplicatesFound": (1 if dup.get("isDuplicate") else 0, "Count"),
        "CostUsd": (cost, "None"),
        "EndToEndLatencyMs": (e2e_ms, "Milliseconds"),
        "ClassifyLatencyMs": (cls.get("latencyMs", 0), "Milliseconds"),
        "Confidence": (float(cls.get("confidence", 0)), "None"),
    })
    return {"ticketId": ticket_id, "status": status, "reviewReasons": reasons}


def fail_handler(event, _context):
    err = event.get("error") or {}
    storage.update(table(), event["ticketId"], {
        "status": storage.STATUS_FAILED,
        "error": {"type": err.get("Error", "Unknown"), "cause": str(err.get("Cause", ""))[:1000]},
    })
    emit({"TicketsFailed": (1, "Count")})
    return {"ticketId": event["ticketId"], "status": storage.STATUS_FAILED}

