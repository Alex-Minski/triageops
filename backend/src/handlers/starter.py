"""SQS -> Step Functions.

Each message starts one Standard workflow execution named after the ticket ID.
Execution names are unique, so a redelivered message cannot triage a ticket
twice. The event source mapping's maximum concurrency caps how fast we start
workflows, which keeps us under Bedrock's request quotas.
"""

from __future__ import annotations

import json
import logging

from triageops.aws import client
from triageops.config import get_settings

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, _context, sfn=None):
    sfn = sfn or client("stepfunctions")
    arn = get_settings().state_machine_arn
    failures = []
    for record in event.get("Records", []):
        try:
            ticket_id = json.loads(record["body"])["ticketId"]
            sfn.start_execution(stateMachineArn=arn, name=ticket_id,
                                input=json.dumps({"ticketId": ticket_id}))
        except sfn.exceptions.ExecutionAlreadyExists:
            log.info(json.dumps({"msg": "already started", "messageId": record["messageId"]}))
        except Exception:  # noqa: BLE001 - report per-message failure, SQS retries just that one
            log.exception("failed to start execution")
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
