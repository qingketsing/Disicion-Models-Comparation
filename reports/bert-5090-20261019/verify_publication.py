"""Verify the published evidence without calling a model or requiring a GPU."""

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from decisionbench.bert_analysis import paired_accuracy  # noqa: E402
from decisionbench.metrics import quality_metrics  # noqa: E402


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def equal(actual, expected):
    if isinstance(actual, float):
        assert math.isclose(actual, float(expected), rel_tol=1e-12, abs_tol=1e-12), (
            actual,
            expected,
        )
    else:
        assert actual == expected, (actual, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", action="store_true", help="Also verify restored raw run files")
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError("Run without Python -O: assertions are the verification checks")

    publication = read_json(HERE / "publication-manifest.json")
    for name, expected in publication["files_sha256"].items():
        equal(digest(HERE / name), expected)
    actual_files = {
        p.relative_to(HERE).as_posix()
        for p in HERE.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    equal(actual_files, set(publication["files_sha256"]) | {"publication-manifest.json"})
    plan_hash = digest(HERE / "frozen-plan/plan.json")
    equal(plan_hash, read_json(HERE / "frozen-plan/plan.sha256.json")["plan_sha256"])

    labels = read_json(HERE / "data-provenance/catalog.json")["labels"]
    equal(len(labels), 60)
    samples = read_csv(HERE / "sample-predictions.csv")
    equal(len(samples), 2974)
    equal(len({s["sample_id"] for s in samples}), 2974)
    summary = read_json(HERE / "quality-summary.json")
    selected = max(
        summary["seeds"], key=lambda s: (s["dev_macro_f1"], s["dev_accuracy"], -s["seed"])
    )
    equal(selected["seed"], summary["selection"]["seed"])
    equal(summary["selection"], read_json(HERE / "training/selection.json"))
    records, metrics = {}, {}
    for seed in summary["seeds"]:
        number = seed["seed"]
        records[number] = [
            dict(
                sample_id=s["sample_id"],
                expected_label=s["expected_label"],
                prediction=s[f"seed_{number}_prediction"],
                status="ok",
            )
            for s in samples
        ]
        assert all(
            r["expected_label"] in labels and r["prediction"] in labels for r in records[number]
        )
        metric = metrics[number] = quality_metrics(records[number], labels)
        equal([metric["accuracy"]] * 3, seed["test_accuracy"])
        equal([metric["macro_f1"]] * 3, seed["test_macro_f1"])
        equal(seed["repeat_prediction_disagreements"], [0, 0])
        equal(seed["success_rate"], [1.0, 1.0, 1.0])
        equal(
            sum(r["prediction"] == r["expected_label"] for r in records[number]),
            seed["test_correct"],
        )
        metadata = read_json(HERE / f"training/seed-{number}/metadata.json")
        equal(metadata["validation_metrics"]["eval_macro_f1"], seed["dev_macro_f1"])
        equal(metadata["model_version"], seed["model_version"])
    for key, metric_key in (("accuracy", "accuracy"), ("macro_f1", "macro_f1")):
        values = [m[metric_key] for m in metrics.values()]
        equal(statistics.mean(values), summary[f"mean_{key}_across_training_seeds"])
        equal(statistics.stdev(values), summary[f"sample_sd_{key}_across_training_seeds"])

    baseline_summary = read_json(HERE / "baseline-metrics.json")
    baseline_path = ROOT / baseline_summary["source"]
    equal(digest(baseline_path), baseline_summary["source_sha256"])
    baseline = read_csv(baseline_path)
    previous_metrics = {}
    for row in baseline_summary["metrics"]:
        model, repeat = row["model"], row["repeat"]
        previous = [r for r in baseline if int(r["repeat"]) == repeat]
        equal(len(previous), 2974)
        equal(
            {r["sample_id"]: r["expected_label"] for r in previous},
            {r["sample_id"]: r["expected_label"] for r in samples},
        )
        metric = quality_metrics(
            [
                dict(
                    expected_label=r["expected_label"],
                    prediction=r[model + "_prediction"],
                    status="ok",
                )
                for r in previous
            ],
            labels,
        )
        previous_metrics[model, repeat] = metric
        equal(metric["accuracy"], row["accuracy"])
        equal(metric["macro_f1"], row["macro_f1_full60"])
    pairs = read_csv(HERE / "analysis/paired-comparisons.csv")
    equal(len(pairs), 54)
    pair_cache = {}
    for row in pairs:
        key = (int(row["training_seed"]), row["baseline_model"], row["baseline_repeat"])
        if key not in pair_cache:
            previous = [r for r in baseline if r["repeat"] == key[2]]
            pair_cache[key] = paired_accuracy(records[key[0]], previous, key[1] + "_prediction")
        for name in ("difference", "ci95_low", "ci95_high"):
            equal(pair_cache[key][name], row[name])
        equal(int(row["unique_samples"]), 2974)
        equal(int(row["bootstrap_draws"]), 2000)
        equal(int(row["seed"]), 42)
    support = read_json(HERE / "training/seed-42/overlap-audit.json")["train_support"]
    classes = read_csv(HERE / "per-class-comparison.csv")
    equal(len(classes), 60)
    for row in classes:
        label = row["label"]
        metric = metrics[selected["seed"]]["per_class"][label]
        equal(int(row["train_support"]), support[label])
        equal(int(row["test_support"]), metric["support"])
        for name in ("precision", "recall", "f1"):
            equal(float(metric[name]), row[f"bert_{name}"])
        jev_f1 = statistics.mean(
            previous_metrics["jev", r]["per_class"][label]["f1"] for r in (1, 2, 3)
        )
        equal(jev_f1, row["jev_mean_f1"])
        equal(float(metric["f1"] - jev_f1), row["bert_minus_jev_f1"])

    runs = read_csv(HERE / "analysis/runs.csv")
    windows = read_csv(HERE / "analysis/steady-60s-windows.csv")
    equal(len(runs), 15)
    equal(len(windows), 12)
    equal(sum(int(r["requests"]) for r in runs), 61326)
    audit = read_json(HERE / "analysis/audit.json")
    equal(audit["capacity_points"], [])
    equal({r["run"] for r in runs}, set(audit["inputs"]))
    for row in runs:
        equal(row["synthetic"], "False")
        equal(row["plan_sha256"], plan_hash)
        recomputed = read_json(HERE / "analysis" / (Path(row["run"]).name + "-recomputed.json"))
        run_summary = recomputed["summary"]
        equal(int(row["requests"]), run_summary["offered_requests"])
        equal(run_summary["success_rate"], row["success_rate"])
        equal(run_summary["latency_attempted"]["p95_ms"], row["p95_ms"])
        if row["mode"] == "quality":
            equal(int(row["requests"]), 2974)
            equal(metrics[int(row["training_seed"])]["accuracy"], row["accuracy"])
            equal(metrics[int(row["training_seed"])]["macro_f1"], row["macro_f1_full"])
        else:
            equal(row["stage"], "pilot")
            equal(float(row["duration_s"]), 120.0)
            equal(row["passed"], str(float(row["offered_rps"]) == 32))
            equal(row["windows_passed"], row["passed"])
            for window in [w for w in windows if w["run"] == row["run"]]:
                source = recomputed["windows"][int(window["window"])]
                equal(int(window["requests"]), source["offered_requests"])
                equal(source["latency_attempted"]["p95_ms"], window["p95_ms"])
                equal(source["success_rate"], window["success_rate"])
                equal(str(source["slo_capacity_candidate"]), window["passed"])
        if args.raw:
            for name, expected in audit["inputs"][row["run"]].items():
                equal(digest(ROOT / row["run"] / name), expected)
            if row["mode"] == "quality":
                raw = [
                    json.loads(line)
                    for line in (ROOT / row["run"] / "requests.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                equal(
                    [{k: r[k] for k in records[int(row["training_seed"])][0]} for r in raw],
                    records[int(row["training_seed"])],
                )
                assert all(r["model_version"] == row["model_version"] for r in raw)
    print(
        json.dumps(
            {
                "status": "PASS",
                "publication_files": len(publication["files_sha256"]),
                "unique_test_samples": 2974,
                "training_seeds": 3,
                "quality_runs": 9,
                "pilot_runs": 6,
                "paired_rows": 54,
                "windows": 12,
                "raw_hashes_verified": args.raw,
                "capacity_points": [],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
