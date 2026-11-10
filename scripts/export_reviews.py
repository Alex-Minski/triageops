"""Export human-reviewed tickets as labeled rows, to grow the evaluation set.

Writes eval/data/reviewed.csv with the same columns as the other splits. The
text is the masked text, so no PII leaves DynamoDB.
"""

from __future__ import annotations

import csv

import boto3
from boto3.dynamodb.conditions import Key

from common import ROOT, outputs, region


def main() -> None:
    tbl = boto3.resource("dynamodb", region_name=region()).Table(outputs()["TableName"])
    items, kwargs = [], {"IndexName": "byStatus", "KeyConditionExpression": Key("status").eq("reviewed")}
    while True:
        resp = tbl.query(**kwargs)
        items += resp["Items"]
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    path = ROOT / "eval" / "data" / "reviewed.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["title", "description", "category", "priority", "team"])
        w.writeheader()
        for it in items:
            r = it["review"]
            w.writerow({"title": it.get("title", ""), "description": it.get("description", ""),
                        "category": r["category"], "priority": r["priority"], "team": r["team"]})
    print(f"wrote {len(items)} reviewed tickets to {path}")


if __name__ == "__main__":
    main()
