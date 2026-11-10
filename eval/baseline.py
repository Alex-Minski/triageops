"""TF-IDF + logistic regression baseline: the number the LLM has to beat.

Trains on train.csv, tunes C on val.csv, reports once on test.csv.
"""

from __future__ import annotations

import time

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import make_pipeline

from common import label_metrics, load_split, record


def text(df):
    return (df["title"] + " \n " + df["description"]).tolist()


def fit(train, val, label: str):
    best, best_f1 = None, -1.0
    for c in (0.3, 1.0, 3.0, 10.0):
        model = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                              LogisticRegression(C=c, max_iter=2000, class_weight="balanced"))
        model.fit(text(train), train[label])
        f1 = f1_score(val[label], model.predict(text(val)), average="macro")
        if f1 > best_f1:
            best, best_f1 = model, f1
    return best


def main() -> None:
    train, val, test = load_split("train"), load_split("val"), load_split("test")
    metrics: dict = {"n": len(test)}
    preds = {}
    started = time.perf_counter()
    for label, prefix in [("category", "category"), ("priority", "priority"), ("team", "team")]:
        model = fit(train, val, label)
        preds[label] = model.predict(text(test))
        metrics.update(label_metrics(test[label], preds[label], prefix))
    joint = (preds["category"] == test["category"].values) & (preds["priority"] == test["priority"].values)
    metrics["jointAccuracy"] = round(float(joint.mean()), 4)
    metrics["msPerTicket"] = round((time.perf_counter() - started) * 1000 / len(test), 3)
    path = record("baseline", {"model": "tfidf+logreg", "train": len(train)}, metrics)
    for k, v in metrics.items():
        print(f"{k:>20}: {v}")
    print(f"saved {path}")


if __name__ == "__main__":
    main()
