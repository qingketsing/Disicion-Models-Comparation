"""Small, dependency-light helpers shared by training, deployment and tests."""

import importlib.metadata
import platform
import subprocess
import sys
from collections import Counter

from decisionbench.metrics import quality_metrics


def overlap_report(train, validation):
    shared = {s.text for s in train} & {s.text for s in validation}
    return {
        "policy": "retain_native_splits",
        "exact_shared_texts": len(shared),
        "train_rows": sum(s.text in shared for s in train),
        "validation_rows": sum(s.text in shared for s in validation),
        "train_size": len(train),
        "validation_size": len(validation),
        "train_support": dict(Counter(s.label for s in train)),
        "validation_support": dict(Counter(s.label for s in validation)),
    }


def classification_metrics(expected, predicted, labels):
    records = [
        {"status": "ok", "expected_label": labels[int(y)], "prediction": labels[int(p)]}
        for y, p in zip(expected, predicted, strict=True)
    ]
    metrics = quality_metrics(records, labels)
    return {
        "accuracy": metrics["accuracy"],
        "macro_f1": metrics["macro_f1"],
        "macro_f1_supported": metrics["macro_f1_supported_classes"],
    }


def environment_info():
    packages = {}
    for name in ("torch", "transformers", "datasets", "accelerate", "numpy", "tokenizers"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        gpu = None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "nvidia_smi": gpu,
    }
