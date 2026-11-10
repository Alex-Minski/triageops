"""Turn a labeled ticket CSV into train/validation/test splits with TriageOps labels.

Default input is the synthetic set. For meaningful numbers, download a public
labeled IT-ticket dataset (Kaggle and Hugging Face have several), then map its
columns and label values onto the TriageOps taxonomy:

  python eval/prepare_data.py --input my_tickets.csv \
      --title-col subject --body-col body --category-col queue --priority-col priority \
      --label-map eval/label_map.example.json

The test split is written once and should then stay locked: tune prompts and
thresholds on validation only, or your test score stops meaning anything.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

DATA = Path(__file__).parent / "data"
DEFAULT_TEAM = {"access": "identity", "hardware": "desktop_support", "software": "desktop_support",
                "network": "network_ops", "email": "applications", "security": "security_ops"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(DATA / "synthetic_tickets.csv"))
    ap.add_argument("--title-col", default="title")
    ap.add_argument("--body-col", default="description")
    ap.add_argument("--category-col", default="category")
    ap.add_argument("--priority-col", default="priority")
    ap.add_argument("--team-col", default="team")
    ap.add_argument("--label-map", help="JSON: {'category': {src: dst}, 'priority': {src: dst}}")
    ap.add_argument("--max-rows", type=int, default=3000)
    ap.add_argument("--force", action="store_true", help="overwrite an existing locked test split")
    args = ap.parse_args()

    if (DATA / "test.csv").exists() and not args.force:
        raise SystemExit("test.csv already exists and is locked. Pass --force only if you really mean to re-split.")

    df = pd.read_csv(args.input)
    mapping = json.loads(Path(args.label_map).read_text()) if args.label_map else {}
    out = pd.DataFrame({
        "title": df[args.title_col].fillna("").astype(str).str.slice(0, 200),
        "description": df[args.body_col].fillna("").astype(str).str.slice(0, 4000),
        "category": df[args.category_col].astype(str).str.strip(),
        "priority": df[args.priority_col].astype(str).str.strip(),
    })
    if mapping.get("category"):
        out["category"] = out["category"].map(mapping["category"])
    if mapping.get("priority"):
        out["priority"] = out["priority"].map(mapping["priority"])
    out["team"] = df[args.team_col] if args.team_col in df.columns else out["category"].map(DEFAULT_TEAM)
    before = len(out)
    out = out.dropna(subset=["category", "priority"])
    out = out[out["title"].str.len() + out["description"].str.len() > 10]
    out = out[out["category"].isin(DEFAULT_TEAM) & out["priority"].isin(["P1", "P2", "P3", "P4"])]
    print(f"kept {len(out)} of {before} rows after label mapping and cleaning")
    out = out.sample(n=min(len(out), args.max_rows), random_state=7)

    train, rest = train_test_split(out, test_size=0.4, stratify=out["category"], random_state=7)
    val, test = train_test_split(rest, test_size=0.5, stratify=rest["category"], random_state=7)
    for name, part in [("train", train), ("val", val), ("test", test)]:
        part.to_csv(DATA / f"{name}.csv", index=False)
        print(f"{name}: {len(part)} rows  {part['category'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
