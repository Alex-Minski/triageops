"""Pick the duplicate threshold from labeled pairs instead of guessing.

Embeds both sides of each pair with Titan Text Embeddings V2 (cached on disk so
reruns are free), sweeps similarity thresholds, and reports precision, recall
and F1. Put the chosen value in infra/cdk.json as duplicateThreshold.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from common import DATA, RESULTS, record
from triageops import dedupe


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="amazon.titan-embed-text-v2:0")
    ap.add_argument("--pairs", default=str(DATA / "dupe_pairs.csv"))
    args = ap.parse_args()

    pairs = pd.read_csv(args.pairs)
    cache_path = RESULTS / "embed_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    def vec(text: str):
        if text not in cache:
            cache[text] = dedupe.embed(text, args.model)[0]
        return cache[text]

    sims = np.array([dedupe.cosine(vec(a), vec(b)) for a, b in zip(pairs["text_a"], pairs["text_b"])])
    RESULTS.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    y = pairs["is_duplicate"].to_numpy().astype(bool)

    rows = []
    for t in np.arange(0.50, 0.99, 0.01):
        p = sims >= t
        tp, fp, fn = int((p & y).sum()), int((p & ~y).sum()), int((~p & y).sum())
        prec = tp / (tp + fp) if tp + fp else 1.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        rows.append({"threshold": round(float(t), 2), "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)})
    table = pd.DataFrame(rows)
    best = table.loc[table["f1"].idxmax()]
    print(table.to_string(index=False))
    metrics = {"pairs": len(pairs), "bestThreshold": best["threshold"], "precision": best["precision"],
               "recall": best["recall"], "f1": best["f1"]}
    print(f"\nbest F1 at threshold {best['threshold']}: precision {best['precision']}, recall {best['recall']}")
    print(f"saved {record('dedupe', {'model': args.model}, metrics)}")


if __name__ == "__main__":
    main()
