"""Send sample tickets from the test split through the deployed webhook endpoint.

Useful for filling the dashboard. Tickets go in as Defender-style alerts so the
API key route is used (no login needed).
"""

from __future__ import annotations

import argparse
import csv
import json
import urllib.request
import uuid

import boto3

from common import ROOT, outputs, region


def api_key() -> str:
    key_id = outputs()["WebhookApiKeyId"]
    return boto3.client("apigateway", region_name=region()).get_api_key(apiKey=key_id, includeValue=True)["value"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--file", default=str(ROOT / "eval" / "data" / "test.csv"))
    args = ap.parse_args()

    url = outputs()["ApiUrl"].rstrip("/") + "/webhooks/alerts"
    key = api_key()
    with open(args.file, newline="") as f:
        rows = list(csv.DictReader(f))[: args.count]
    for row in rows:
        body = json.dumps({"alertId": f"seed-{uuid.uuid4().hex[:12]}", "title": row["title"],
                           "description": row["description"], "severity": "informational"}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "x-api-key": key})
        with urllib.request.urlopen(req) as resp:
            print(resp.status, json.loads(resp.read())["ticketId"], row["title"][:60])


if __name__ == "__main__":
    main()
