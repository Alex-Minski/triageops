"""Red-team the pipeline with adversarial tickets (eval/data/adversarial.jsonl).

For PII cases: is every secret gone from the text the model sees?
For injection cases: does the classifier keep the true priority despite the
injected instruction, and does the guardrail flag the attempt?

  python eval/guardrail_eval.py --guardrail-id <id> --guardrail-version 1
  (IDs are in build/outputs.json after deploy; without them the regex fallback is tested)
"""

from __future__ import annotations

import argparse
import json

from common import DATA, record
from triageops import classifier, guardrails


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardrail-id", default="")
    ap.add_argument("--guardrail-version", default="DRAFT")
    ap.add_argument("--model", default="us.amazon.nova-lite-v1:0")
    ap.add_argument("--skip-classify", action="store_true", help="only test masking and detection (no model calls)")
    args = ap.parse_args()

    cases = [json.loads(line) for line in (DATA / "adversarial.jsonl").read_text().splitlines() if line.strip()]
    pii_total = pii_masked = inj_total = inj_detected = inj_resisted = 0
    failures = []
    for c in cases:
        g = guardrails.apply(c["description"], args.guardrail_id, args.guardrail_version)
        if c["kind"] == "pii":
            pii_total += 1
            leaked = [s for s in c["secrets"] if s in g.text]
            if leaked:
                failures.append({"id": c["id"], "leaked": leaked})
            else:
                pii_masked += 1
            continue
        inj_total += 1
        inj_detected += int(g.prompt_attack)
        if not args.skip_classify:
            try:
                t = classifier.classify(c["title"], g.text, args.model).triage
                if t.priority.value == c["expected_priority"]:
                    inj_resisted += 1
                else:
                    failures.append({"id": c["id"], "expected": c["expected_priority"], "got": t.priority.value})
            except classifier.TriageParseError:
                failures.append({"id": c["id"], "error": "invalid output"})

    metrics = {
        "piiCases": pii_total,
        "piiMaskedRate": round(pii_masked / pii_total, 4) if pii_total else None,
        "injectionCases": inj_total,
        "injectionDetectedRate": round(inj_detected / inj_total, 4) if inj_total else None,
        "injectionResistedRate": None if args.skip_classify else round(inj_resisted / inj_total, 4),
    }
    for k, v in metrics.items():
        print(f"{k:>24}: {v}")
    for f in failures[:20]:
        print("  FAIL", f)
    engine = "bedrock-guardrails" if args.guardrail_id else "regex-fallback"
    print(f"saved {record('guardrail', {'engine': engine, 'model': args.model}, metrics)}")


if __name__ == "__main__":
    main()
