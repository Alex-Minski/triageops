"""Duplicate and recurring-issue detection with Titan embeddings and S3 Vectors.

Each triaged ticket is embedded and stored in an S3 Vectors index (cosine
distance). A new ticket queries the index first; any neighbour whose
similarity (1 - cosine distance) passes the threshold is reported as a likely
duplicate. Tune the threshold with eval/dedupe_eval.py, not by eye.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .pricing import Usage

EMBED_DIMENSIONS = 1024  # must match the S3 Vectors index dimension in the CDK stack


@dataclass
class Neighbour:
    ticket_id: str
    title: str
    category: str
    similarity: float

    def as_dict(self) -> dict:
        return {"ticketId": self.ticket_id, "title": self.title,
                "category": self.category, "similarity": round(self.similarity, 4)}


def embed(text: str, model_id: str, client=None) -> tuple[list[float], Usage]:
    if client is None:
        from .aws import client as get_client
        client = get_client("bedrock-runtime")
    resp = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text[:20_000], "dimensions": EMBED_DIMENSIONS, "normalize": True}),
    )
    body = json.loads(resp["body"].read())
    return body["embedding"], Usage(input_tokens=int(body.get("inputTextTokenCount", 0)))


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def find_similar(vector: list[float], vector_bucket: str, index: str, exclude_id: str,
                 top_k: int = 5, client=None) -> list[Neighbour]:
    if client is None:
        from .aws import client as get_client
        client = get_client("s3vectors")
    resp = client.query_vectors(
        vectorBucketName=vector_bucket,
        indexName=index,
        topK=top_k + 1,
        queryVector={"float32": vector},
        returnMetadata=True,
        returnDistance=True,
    )
    out = []
    for v in resp.get("vectors", []):
        if v["key"] == exclude_id:
            continue
        meta = v.get("metadata") or {}
        out.append(Neighbour(
            ticket_id=v["key"],
            title=str(meta.get("title", "")),
            category=str(meta.get("category", "")),
            similarity=1.0 - float(v.get("distance", 1.0)),
        ))
    return sorted(out, key=lambda n: n.similarity, reverse=True)[:top_k]


def store(ticket_id: str, vector: list[float], title: str, category: str, created_at: str,
          vector_bucket: str, index: str, client=None) -> None:
    if client is None:
        from .aws import client as get_client
        client = get_client("s3vectors")
    client.put_vectors(
        vectorBucketName=vector_bucket,
        indexName=index,
        vectors=[{
            "key": ticket_id,
            "data": {"float32": vector},
            "metadata": {"title": title[:200], "category": category, "createdAt": created_at},
        }],
    )
