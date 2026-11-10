import json
from datetime import datetime, timezone

import boto3

from triageops import storage


def _post(resource, body, headers=None):
    return {"resource": resource, "httpMethod": "POST", "body": json.dumps(body), "headers": headers or {}}


def _messages(queue_url):
    sqs = boto3.client("sqs", region_name="us-east-1")
    return sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get("Messages", [])


def test_ingest_creates_ticket_and_enqueues(aws):
    from handlers import ingest

    resp = ingest.handler(_post("/tickets", {"title": "VPN down", "description": "Gateway timeout"}), None)
    assert resp["statusCode"] == 202
    ticket_id = json.loads(resp["body"])["ticketId"]

    item = storage.get(boto3.resource("dynamodb").Table("tickets-test"), ticket_id)
    assert item["status"] == "queued" and item["title"] == "(processing)"
    raw = boto3.client("s3").get_object(Bucket="raw-test", Key=item["rawKey"])["Body"].read()
    assert json.loads(raw)["description"] == "Gateway timeout"
    assert json.loads(_messages(aws["queue_url"])[0]["Body"]) == {"ticketId": ticket_id}


def test_webhook_is_idempotent(aws):
    from handlers import ingest

    alert = {"alertId": "da-42", "title": "Malware detected", "severity": "high"}
    first = ingest.handler(_post("/webhooks/alerts", alert), None)
    second = ingest.handler(_post("/webhooks/alerts", alert), None)
    assert first["statusCode"] == 202 and second["statusCode"] == 200
    assert json.loads(first["body"])["ticketId"] == json.loads(second["body"])["ticketId"]
    assert len(_messages(aws["queue_url"])) == 1


def test_ingest_rejects_invalid(aws):
    from handlers import ingest

    assert ingest.handler(_post("/tickets", {"title": "   ", "description": "x"}), None)["statusCode"] == 400
    bad_json = {"resource": "/tickets", "httpMethod": "POST", "body": "{not json"}
    assert ingest.handler(bad_json, None)["statusCode"] == 400


class FakeSfn:
    class exceptions:
        class ExecutionAlreadyExists(Exception):
            pass

    def __init__(self):
        self.started = []

    def start_execution(self, **kw):
        if kw["name"] == "T-dup":
            raise self.exceptions.ExecutionAlreadyExists()
        if kw["name"] == "T-boom":
            raise RuntimeError("throttled")
        self.started.append(kw["name"])


def test_starter_reports_only_real_failures():
    from handlers import starter

    recs = [{"messageId": m, "body": json.dumps({"ticketId": t})}
            for m, t in [("m1", "T-ok"), ("m2", "T-dup"), ("m3", "T-boom")]]
    sfn = FakeSfn()
    out = starter.handler({"Records": recs}, None, sfn=sfn)
    assert sfn.started == ["T-ok"]
    assert out == {"batchItemFailures": [{"itemIdentifier": "m3"}]}


def test_review_reasons_and_cost():
    from handlers import steps

    state = {"mask": {"promptAttack": True},
             "classification": {"confidence": 0.4, "costUsd": 0.0001},
             "duplicates": {"embedCostUsd": 0.00001}, "draft": {"costUsd": 0.001}}
    assert steps.review_reasons(state, 0.7) == ["low_confidence", "possible_prompt_injection"]
    assert steps.review_reasons({"classification": {"parseError": "x"}}, 0.7) == ["invalid_model_output"]
    assert steps.review_reasons({"classification": {"confidence": 0.95}, "mask": {}}, 0.7) == []
    assert steps.total_cost(state) == 0.00111


def test_mask_and_finalize_with_regex_fallback(aws):
    from handlers import ingest, steps

    resp = ingest.handler(_post("/tickets", {
        "title": "Locked out", "description": "I'm bob@corp.com, call 416-555-0100"}), None)
    tid = json.loads(resp["body"])["ticketId"]

    mask = steps.mask_handler({"ticketId": tid}, None)
    assert "{EMAIL}" in mask["description"] and "bob@corp.com" not in mask["description"]
    assert mask["engine"] == "regex-fallback"

    state = {"ticketId": tid, "mask": mask,
             "classification": {"category": "access", "priority": "P2", "team": "identity",
                                "confidence": 0.93, "costUsd": 0.0002, "latencyMs": 640},
             "duplicates": {"neighbours": [], "isDuplicate": False}, "draft": {"skipped": True}}
    out = steps.finalize_handler(state, None)
    assert out["status"] == "triaged"
    item = storage.get(boto3.resource("dynamodb").Table("tickets-test"), tid)
    assert item["triage"]["category"] == "access" and item["costUsd"] == 0.0002
    assert "bob@corp.com" not in json.dumps(item)


def test_api_list_get_review_stats(aws):
    from handlers import api, ingest, steps

    tid = json.loads(ingest.handler(_post("/tickets", {"title": "Printer jam", "description": "3rd floor"}), None)["body"])["ticketId"]
    mask = steps.mask_handler({"ticketId": tid}, None)
    steps.finalize_handler({"ticketId": tid, "mask": mask, "classification": {
        "category": "hardware", "priority": "P3", "team": "desktop_support", "confidence": 0.5}}, None)

    listed = api.handler({"httpMethod": "GET", "resource": "/tickets",
                          "queryStringParameters": {"status": "needs_review"}}, None)
    assert [i["ticketId"] for i in json.loads(listed["body"])["items"]] == [tid]

    got = api.handler({"httpMethod": "GET", "resource": "/tickets/{ticketId}", "pathParameters": {"ticketId": tid}}, None)
    assert "rawKey" not in json.loads(got["body"])

    review = {"httpMethod": "POST", "resource": "/tickets/{ticketId}/review", "pathParameters": {"ticketId": tid},
              "body": json.dumps({"category": "hardware", "priority": "P4", "team": "desktop_support"}),
              "requestContext": {"authorizer": {"claims": {"email": "alex@example.com"}}}}
    r = json.loads(api.handler(review, None)["body"])
    assert r["status"] == "reviewed" and r["agreedWithModel"] is False

    stats = json.loads(api.handler({"httpMethod": "GET", "resource": "/stats"}, None)["body"])
    assert stats["total"] == 1 and stats["byPriority"] == {"P4": 1} and stats["reviewAgreementRate"] == 0.0


def test_compute_stats_clusters_and_percentiles():
    from handlers.api import compute_stats

    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    items = [
        {"ticketId": "A", "status": "triaged", "title": "VPN down", "createdAt": "2026-11-10T09:00:00",
         "triage": {"category": "network", "priority": "P2"}, "costUsd": 0.001, "e2eLatencyMs": 1000},
        {"ticketId": "B", "status": "triaged", "title": "VPN again", "createdAt": "2026-11-10T10:00:00",
         "triage": {"category": "network", "priority": "P2"}, "costUsd": 0.003, "e2eLatencyMs": 3000,
         "duplicateOf": "A"},
        {"ticketId": "C", "status": "needs_review", "title": "?", "createdAt": "2026-11-09T10:00:00",
         "triage": {"category": "software", "priority": "P3"}},
    ]
    s = compute_stats(items, now)
    assert s["byCategory"] == {"network": 2, "software": 1}
    assert s["autoTriageRate"] == round(2 / 3, 4)
    assert s["costUsd"]["per1000Tickets"] == 2.0
    assert s["latencyMs"]["p50"] == 2000
    assert s["recurring"] == [{"ticketId": "A", "title": "VPN down", "duplicates": 1}]
    assert s["daily"][-1] == {"date": "2026-11-10", "count": 2}
