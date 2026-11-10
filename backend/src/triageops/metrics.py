"""CloudWatch custom metrics through the Embedded Metric Format (EMF).

Printing one structured JSON line is enough: CloudWatch Logs extracts the
metrics asynchronously, so there is no PutMetricData call on the hot path.
"""

from __future__ import annotations

import json
import time

NAMESPACE = "TriageOps"


def emit(metrics: dict[str, tuple[float, str]], dimensions: dict[str, str] | None = None) -> None:
    """metrics: name -> (value, unit), e.g. {"CostUsd": (0.0004, "None")}."""
    dimensions = dimensions or {}
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": NAMESPACE,
                "Dimensions": [list(dimensions.keys())] if dimensions else [[]],
                "Metrics": [{"Name": n, "Unit": u} for n, (_, u) in metrics.items()],
            }],
        },
        **dimensions,
        **{n: v for n, (v, _) in metrics.items()},
    }
    print(json.dumps(record))
