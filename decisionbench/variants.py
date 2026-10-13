"""Frozen, nested candidate catalogs evaluated on identical anchor samples."""

import random
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json
from decisionbench.protocol import Catalog, Sample


def scale_variants(samples: list[Sample], catalog: Catalog, sizes, seed, per_class):
    sizes = sorted(set(sizes))
    if not sizes or any(type(k) is not int or k < 2 for k in sizes):
        raise ValueError("candidate sizes must be integers >= 2")
    if sizes[-1] > len(catalog.labels) or type(per_class) is not int or per_class < 1:
        raise ValueError("invalid maximum catalog size or samples per anchor class")
    buckets = defaultdict(list)
    for sample in samples:
        buckets[sample.label].append(sample)
    eligible = sorted(label for label, rows in buckets.items() if len(rows) >= per_class)
    if len(eligible) < sizes[0]:
        raise ValueError("not enough classes with the required anchor sample count")
    rng = random.Random(seed)
    anchors = rng.sample(eligible, sizes[0])
    distractors = sorted(set(catalog.labels) - set(anchors))
    rng.shuffle(distractors)
    selected = []
    for label in sorted(anchors):
        selected.extend(rng.sample(sorted(buckets[label], key=lambda s: s.sample_id), per_class))
    rng.shuffle(selected)
    catalogs = {}
    for size in sizes:
        # Common labels retain the same relative order across all candidate sizes.
        labels = sorted(anchors + distractors[: size - sizes[0]])
        catalogs[size] = Catalog(
            f"{catalog.version}-scale-{size}-seed-{seed}",
            {label: catalog.labels[label] for label in labels},
            catalog.reject_label if catalog.reject_label in labels else None,
        )
    return selected, catalogs, sorted(anchors)


def write_samples(path: Path, samples):
    import json

    path.write_text(
        "".join(json.dumps(asdict(s), ensure_ascii=False) + "\n" for s in samples),
        encoding="utf-8",
    )


def write_catalog(path: Path, catalog: Catalog):
    write_json(path, asdict(catalog))
    return file_hash(path)
