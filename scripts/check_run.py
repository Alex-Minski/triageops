"""After a load test: did every ticket finish, and did anything land in the DLQ?

  python scripts/check_run.py --since 2026-11-20T15:00:00Z

Reports tickets created since the given time by status, end-to-end latency
percentiles, the tickets finished per minute, and the DLQ depth. These are the
numbers behind a bullet like "sustained N tickets/min with zero dropped messages".
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime

import boto3

from common import outputs, region


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="ISO time, e.g. 2026-11-20T15:00:00Z")
    args = ap.parse_args()
    since = args.since.replace("Z", "+00:00")

    out = outputs()
    tbl = boto3.resource("dynamodb", region_name=region()).Table(out["TableName"])
    items, kwargs = [], {"ProjectionExpression": "ticketId, #s, createdAt, triagedAt, e2eLatencyMs",
                         "ExpressionAttributeNames": {"#s": "status"}}
    while True:
        resp = tbl.scan(**kwargs)
        items += [i for i in resp["Items"] if i.get("createdAt", "") >= since]
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    statuses = Counter(i["status"] for i in items)
    lat = sorted(float(i["e2eLatencyMs"]) for i in items if "e2eLatencyMs" in i)
    done = [i for i in items if "triagedAt" in i]
    print(f"tickets since {args.since}: {len(items)}  by status: {dict(statuses)}")
    if lat:
        print(f"end-to-end latency p50 {lat[len(lat) // 2]:.0f} ms, p95 {lat[int(len(lat) * 0.95) - 1]:.0f} ms")
    if len(done) > 1:
        t = sorted(datetime.fromisoformat(i["triagedAt"]) for i in done)
        minutes = max((t[-1] - t[0]).total_seconds() / 60, 1 / 60)
        print(f"throughput: {len(done) / minutes:.1f} tickets/min finished")

    sqs = boto3.client("sqs", region_name=region())
    for q in sqs.list_queues(QueueNamePrefix="TriageOps-TriageDLQ").get("QueueUrls", []):
        n = sqs.get_queue_attributes(QueueUrl=q, AttributeNames=["ApproximateNumberOfMessages"])
        print(f"DLQ messages: {n['Attributes']['ApproximateNumberOfMessages']}")


if __name__ == "__main__":
    main()
