"""Offline BERT analysis using the same request accounting as the harness."""

import math
from collections import defaultdict
from dataclasses import replace

from decisionbench.metrics import summarize


def steady_windows(records, config, labels, width_s=60):
    if config.mode != "load":
        raise ValueError("steady windows require a load run")
    if width_s <= 0:
        raise ValueError("window width must be positive")
    expected = sum(
        i / config.offered_rps < config.duration_s
        for i in range(math.ceil(config.offered_rps * config.duration_s))
    )
    if len(records) != expected:
        raise ValueError("request count differs from the planned arrival count")
    if len({r["request_id"] for r in records}) != len(records):
        raise ValueError("duplicate request_id")
    if any(not 0 <= r["scheduled_s"] < config.duration_s for r in records):
        raise ValueError("arrival outside the planned window")
    if any(
        not math.isclose(row["scheduled_s"], i / config.offered_rps, abs_tol=1e-6)
        for i, row in enumerate(sorted(records, key=lambda r: r["scheduled_s"]))
    ):
        raise ValueError("arrival schedule differs from the planned fixed-rate schedule")
    windows = []
    for i in range(math.ceil(config.duration_s / width_s)):
        start, end = i * width_s, min((i + 1) * width_s, config.duration_s)
        rows = [r for r in records if start <= r["scheduled_s"] < end]
        elapsed = max(end, max((r["completed_s"] for r in rows), default=end)) - start
        # Window drain intervals can overlap; don't add their costs together.
        window_config = replace(config, duration_s=end - start, cost={})
        summary = summarize(rows, window_config, elapsed, labels)
        summary.update(
            window=i,
            start_s=start,
            end_s=end,
            attribution="scheduled arrival; completion may be after window end",
        )
        windows.append(summary)
    return windows


def confirmed_capacities(items, required_repeats=None):
    groups = defaultdict(list)
    for item in items:
        if item["stage"] == "formal" and item["mode"] == "load":
            groups[
                (
                    item["model_version"],
                    item["device"],
                    item["plan_sha256"],
                    item["network_note"],
                    item["offered_rps"],
                )
            ].append(item)
    capacities = []
    for (version, device, plan, network, rps), group in sorted(groups.items()):
        required = required_repeats or group[0].get("required_repeats", 3)
        repeats = {r["repeat"] for r in group}
        passed = (
            required >= 3
            and len(group) == required
            and all(r.get("required_repeats", 3) == required for r in group)
            and repeats == set(range(1, required + 1))
            and all(
                r["duration_s"] >= 300
                and r["passed"]
                and r["windows_passed"]
                and not r["synthetic"]
                for r in group
            )
        )
        capacities.append(
            {
                "model_version": version,
                "device": device,
                "plan_sha256": plan,
                "network_note": network,
                "offered_rps": rps,
                "confirmed": passed,
                "run_count": len(group),
                "repeats": sorted(repeats),
            }
        )
    return capacities


def paired_accuracy(records, baseline, prediction_column, draws=2000, seed=42):
    import numpy as np

    if len({r["sample_id"] for r in records}) != len(records):
        raise ValueError("quality comparison needs unique sample IDs, not repeated load requests")
    current = {r["sample_id"]: r for r in records}
    reference = {r["sample_id"]: r for r in baseline}
    if len(reference) != len(baseline) or set(current) != set(reference):
        raise ValueError("paired comparison sample IDs do not match")
    differences = []
    for sample_id, row in current.items():
        old = reference[sample_id]
        if row["expected_label"] != old["expected_label"]:
            raise ValueError("paired ground truth differs")
        differences.append(
            int(row["status"] == "ok" and row["prediction"] == row["expected_label"])
            - int(old[prediction_column] == old["expected_label"])
        )
    values = np.asarray(differences, dtype=float)
    rng = np.random.default_rng(seed)
    means = []
    # Bounded allocation: don't allocate a draws x N matrix for larger datasets.
    for offset in range(0, draws, 100):
        indices = rng.integers(0, len(values), size=(min(100, draws - offset), len(values)))
        means.extend(values[indices].mean(axis=1).tolist())
    low, high = np.quantile(means, [0.025, 0.975])
    return {
        "difference": float(values.mean()),
        "ci95_low": float(low),
        "ci95_high": float(high),
        "unique_samples": len(values),
        "bootstrap_draws": draws,
        "seed": seed,
        "unit": "unique sample within one model artifact and one inference repeat",
    }
