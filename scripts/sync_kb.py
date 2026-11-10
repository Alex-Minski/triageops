"""Index the runbooks in S3 into the Bedrock Knowledge Base and wait for it to finish."""

from __future__ import annotations

import sys
import time

import boto3

from common import outputs, region


def main() -> None:
    out = outputs()
    agent = boto3.client("bedrock-agent", region_name=region())
    job = agent.start_ingestion_job(knowledgeBaseId=out["KnowledgeBaseId"], dataSourceId=out["DataSourceId"])["ingestionJob"]
    print(f"ingestion job {job['ingestionJobId']} started")
    while True:
        job = agent.get_ingestion_job(knowledgeBaseId=out["KnowledgeBaseId"], dataSourceId=out["DataSourceId"],
                                      ingestionJobId=job["ingestionJobId"])["ingestionJob"]
        if job["status"] in ("COMPLETE", "FAILED", "STOPPED"):
            break
        time.sleep(5)
    print(f"status: {job['status']}  stats: {job.get('statistics')}")
    if job["status"] != "COMPLETE":
        print(job.get("failureReasons"))
        sys.exit(1)


if __name__ == "__main__":
    main()
