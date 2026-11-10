"""Shared helpers for the operator scripts: read the stack outputs written by `make deploy`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "build" / "outputs.json"


def outputs() -> dict:
    if not OUTPUTS.exists():
        sys.exit(f"{OUTPUTS} not found. Run `make deploy` first (it writes the stack outputs there).")
    return json.loads(OUTPUTS.read_text())["TriageOps"]


def region() -> str:
    return boto3.session.Session().region_name or "us-east-1"
