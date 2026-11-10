"""Shared helpers for the evaluation scripts: data loading, metrics and the results log."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "eval" / "data"
RESULTS = ROOT / "eval" / "results"
sys.path.insert(0, str(ROOT / "backend" / "src"))


def load_split(name: str) -> pd.DataFrame:
    path = DATA / f"{name}.csv"
    if not path.exists():
        raise SystemExit(f"{path} missing. Run: python eval/generate_synthetic.py && python eval/prepare_data.py")
    return pd.read_csv(path).fillna("")


def label_metrics(y_true, y_pred, prefix: str) -> dict:
    return {
        f"{prefix}Accuracy": round(accuracy_score(y_true, y_pred), 4),
        f"{prefix}MacroF1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4),
    }


def percentile(values, pct: float):
    return round(float(np.percentile(values, pct)), 1) if len(values) else None


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return "uncommitted"


def record(kind: str, config: dict, metrics: dict) -> Path:
    """Save a JSON result and append one row to RESULTS.md, so every reported number
    traces back to a dated, reproducible run."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"kind": kind, "timestamp": stamp, "commit": git_commit(), "config": config, "metrics": metrics}
    path = RESULTS / f"{kind}-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2))

    md = RESULTS / "RESULTS.md"
    if not md.exists():
        md.write_text("# Evaluation log\n\nOne row per run. Full details in the matching JSON file.\n\n"
                      "| When (UTC) | Commit | Run | Config | Key metrics |\n| --- | --- | --- | --- | --- |\n")
    cfg = ", ".join(f"{k}={v}" for k, v in config.items())
    key = ", ".join(f"{k}={v}" for k, v in metrics.items() if not isinstance(v, (dict, list)))
    with md.open("a") as f:
        f.write(f"| {stamp} | {payload['commit']} | {kind} | {cfg} | {key} |\n")
    return path
