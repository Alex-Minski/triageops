"""Evaluate the Bedrock classifier on a labeled split, using the same code as the Lambda.

  python eval/run_eval.py                                   # default model, test split
  python eval/run_eval.py --model us.amazon.nova-micro-v1:0 # compare a cheaper model
  python eval/run_eval.py --split val --no-few-shot         # prompt experiments on val only
  python eval/run_eval.py --limit 50                        # quick, cheap smoke run

Reports accuracy and macro-F1 per label, joint accuracy (category AND priority),
the invalid-output rate, latency percentiles, cost per 1,000 tickets, and what
happens at the review threshold: the share auto-triaged and how accurate that
share is. Writes per-ticket predictions for error analysis.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from sklearn.metrics import confusion_matrix

from common import RESULTS, label_metrics, load_split, percentile, record
from triageops import classifier, guardrails
from triageops.pricing import cost_usd


def run_one(row, args):
    title, desc = row["title"], row["description"]
    if args.mask:
        title, desc = guardrails.regex_mask(title).text, guardrails.regex_mask(desc).text
    try:
        res = classifier.classify(title, desc, args.model, few_shot=not args.no_few_shot,
                                  prompt_cache=args.prompt_cache)
        t = res.triage
        return {"pred_category": t.category.value, "pred_priority": t.priority.value, "pred_team": t.team.value,
                "confidence": t.confidence, "latency_ms": res.latency_ms, "input_tokens": res.usage.input_tokens,
                "output_tokens": res.usage.output_tokens, "cache_read": res.usage.cache_read_tokens,
                "cost_usd": res.cost_usd, "attempts": res.attempts, "rationale": t.rationale, "invalid": False}
    except classifier.TriageParseError:
        return {"pred_category": "", "pred_priority": "", "pred_team": "", "confidence": 0.0, "latency_ms": None,
                "cost_usd": None, "attempts": 2, "rationale": "", "invalid": True}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="us.amazon.nova-lite-v1:0")
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--no-few-shot", action="store_true")
    ap.add_argument("--prompt-cache", action="store_true")
    ap.add_argument("--mask", action="store_true", help="apply the regex PII mask first, as production would")
    args = ap.parse_args()

    df = load_split(args.split)
    if args.limit:
        df = df.sample(n=min(args.limit, len(df)), random_state=1)
    rows = df.to_dict("records")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        out = list(pool.map(lambda r: run_one(r, args), rows))
    pred = pd.concat([df.reset_index(drop=True), pd.DataFrame(out)], axis=1)

    ok = pred[~pred["invalid"]]
    m: dict = {"n": len(pred), "invalidRate": round(float(pred["invalid"].mean()), 4)}
    m.update(label_metrics(pred["category"], pred["pred_category"], "category"))
    m.update(label_metrics(pred["priority"], pred["pred_priority"], "priority"))
    m.update(label_metrics(pred["team"], pred["pred_team"], "team"))
    correct = (pred["category"] == pred["pred_category"]) & (pred["priority"] == pred["pred_priority"])
    m["jointAccuracy"] = round(float(correct.mean()), 4)

    auto = pred["confidence"] >= args.threshold
    m["autoTriageShare"] = round(float(auto.mean()), 4)
    m["autoTriageJointAccuracy"] = round(float(correct[auto].mean()), 4) if auto.any() else None
    m["latencyP50Ms"] = percentile(ok["latency_ms"].dropna(), 50)
    m["latencyP95Ms"] = percentile(ok["latency_ms"].dropna(), 95)
    costs = ok["cost_usd"].dropna()
    m["costPer1000TicketsUsd"] = round(float(costs.mean()) * 1000, 4) if len(costs) else None
    m["avgInputTokens"] = round(float(ok["input_tokens"].mean()), 1) if len(ok) else None
    m["retryRate"] = round(float((ok["attempts"] > 1).mean()), 4) if len(ok) else None
    if cost_usd(args.model, classifier.Usage()) is None:
        print(f"note: no price for {args.model} in prices.json, cost not computed")

    config = {"model": args.model, "split": args.split, "fewShot": not args.no_few_shot,
              "promptCache": args.prompt_cache, "mask": args.mask, "threshold": args.threshold}
    path = record("llm", config, m)
    pred_path = RESULTS / (path.stem + "-predictions.csv")
    pred.to_csv(pred_path, index=False)

    for k, v in m.items():
        print(f"{k:>26}: {v}")
    labels = sorted(pred["category"].unique())
    print("\ncategory confusion (rows = truth, cols = predicted):")
    print(pd.DataFrame(confusion_matrix(pred["category"], pred["pred_category"], labels=labels),
                       index=labels, columns=labels).to_string())
    print(f"\nsaved {path}\nsaved {pred_path}  (per-ticket predictions for error analysis)")


if __name__ == "__main__":
    main()
