import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "TABLE_NAME": "tickets-test",
    "RAW_BUCKET": "raw-test",
    "QUEUE_URL": "",
    "STATE_MACHINE_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:test",
    "CLASSIFY_MODEL_ID": "us.amazon.nova-lite-v1:0",
    "DRAFT_MODEL_ID": "us.amazon.nova-pro-v1:0",
})


class FakeBedrock:
    """Minimal stand-in for bedrock-runtime: returns queued responses in order."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        return {"body": io.BytesIO(json.dumps(self.responses.pop(0)).encode())}


def tool_response(payload, input_tokens=300, output_tokens=60):
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t1", "name": "record_triage", "input": payload}}
        ]}},
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
    }


@pytest.fixture
def aws():
    """Moto-backed DynamoDB table, raw bucket and queue matching the CDK stack."""
    import boto3
    from moto import mock_aws

    from triageops import aws as aws_mod
    from triageops import config

    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="tickets-test",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "ticketId", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "ticketId", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[{
                "IndexName": "byStatus",
                "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"},
                              {"AttributeName": "createdAt", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="raw-test")
        queue_url = boto3.client("sqs", region_name="us-east-1").create_queue(QueueName="q")["QueueUrl"]
        os.environ["QUEUE_URL"] = queue_url
        config.get_settings.cache_clear()
        aws_mod.client.cache_clear()
        aws_mod.table.cache_clear()
        yield {"queue_url": queue_url}
        config.get_settings.cache_clear()
        aws_mod.client.cache_clear()
        aws_mod.table.cache_clear()
