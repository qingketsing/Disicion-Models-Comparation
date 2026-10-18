"""Recompute quality, load windows and paired differences; never calls a model."""

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json
from decisionbench.bert_analysis import confirmed_capacities, paired_accuracy, steady_windows
from decisionbench.config import RunConfig
from decisionbench.datasets import load_catalog, read_jsonl
from decisionbench.metrics import summarize


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(run_dirs, out, baseline_path=None, pricing=None):
    if out.exists():
        raise ValueError("analysis output already exists; use a new directory")
    out.mkdir(parents=True)
    baseline = []
    if baseline_path:
        with baseline_path.open(encoding="utf-8-sig", newline="") as stream:
            baseline = list(csv.DictReader(stream))
    run_rows, window_rows, pairs, evidence = [], [], [], {}
    for run_dir in sorted({path.resolve() for path in run_dirs}):
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest["state"] != "completed":
            raise ValueError(f"incomplete run: {run_dir}")
        config = RunConfig(**manifest["config"])
        if pricing:
            config = replace(config, cost=pricing)
        records = read_jsonl(run_dir / "requests.jsonl")
        catalog = load_catalog(run_dir / "inputs/catalog-0.json")
        dataset_path = run_dir / "inputs/dataset.jsonl"
        if file_hash(dataset_path) != manifest["dataset_sha256"]:
            raise ValueError("frozen dataset hash mismatch")
        if file_hash(run_dir / "inputs/catalog-0.json") != manifest["catalog_sha256"][0]:
            raise ValueError("frozen catalog hash mismatch")
        samples = read_jsonl(dataset_path)
        if config.mode == "quality":
            if [r["sample_id"] for r in records] != [s["sample_id"] for s in samples]:
                raise ValueError("quality run is incomplete or input order differs")
            if any(
                r["expected_label"] != s["label"] for r, s in zip(records, samples, strict=True)
            ):
                raise ValueError("quality request labels differ from frozen data")
        summary = summarize(records, config, manifest["elapsed_s"], catalog.labels)
        env = config.environment
        versions = {r["model_version"] for r in records if r["status"] == "ok"}
        if versions and versions != {env["model_version"]}:
            raise ValueError("responses contain an unexpected model version")
        windows = steady_windows(records, config, catalog.labels) if config.mode == "load" else []
        row = {
            "run": str(run_dir),
            "mode": config.mode,
            "stage": env.get("experiment_stage", "unspecified"),
            "model_version": env["model_version"],
            "training_seed": env["training_seed"],
            "repeat": env["repeat"],
            "required_repeats": env.get("required_repeats", 3),
            "device": env["service"]["device"],
            "plan_sha256": env["plan_sha256"],
            "network_note": env["network_note"],
            "synthetic": manifest["synthetic"] or env["service"].get("synthetic", False),
            "duration_s": config.duration_s,
            "offered_rps": config.offered_rps,
            "requests": len(records),
            "success_rate": summary["success_rate"],
            "accuracy": summary["quality"]["accuracy"],
            "macro_f1_full": summary["quality"]["macro_f1"],
            "macro_f1_supported": summary["quality"]["macro_f1_supported_classes"],
            "p95_ms": summary["latency_attempted"]["p95_ms"],
            "max_scheduler_lag_ms": summary["scheduler_lag"]["max_ms"],
            "goodput_qps": summary["goodput_qps"],
            "correct_goodput_qps": summary["correct_goodput_qps"],
            "cost_currency": summary["cost"].get("currency"),
            "measured_cost": summary["cost"].get("total_measured_cost"),
            "cost_per_million_correct": summary["cost"].get("cost_per_million_correct"),
            "cost_per_million_slo_correct": summary["cost"].get("cost_per_million_slo_correct"),
            "passed": summary["slo_capacity_candidate"],
            "windows_passed": bool(windows) and all(w["slo_capacity_candidate"] for w in windows),
        }
        run_rows.append(row)
        evidence[str(run_dir)] = {
            name: file_hash(run_dir / name)
            for name in ("manifest.json", "requests.jsonl", "inputs/dataset.jsonl")
        }
        write_json(
            out / (run_dir.name + "-recomputed.json"), {"summary": summary, "windows": windows}
        )
        for window in windows:
            window_rows.append(
                {
                    "run": str(run_dir),
                    "window": window["window"],
                    "start_s": window["start_s"],
                    "end_s": window["end_s"],
                    "requests": window["offered_requests"],
                    "success_rate": window["success_rate"],
                    "p95_ms": window["latency_attempted"]["p95_ms"],
                    "max_scheduler_lag_ms": window["scheduler_lag"]["max_ms"],
                    "passed": window["slo_capacity_candidate"],
                }
            )
        if config.mode == "quality" and baseline:
            for repeat in sorted({r["repeat"] for r in baseline}):
                original = [r for r in baseline if r["repeat"] == repeat]
                baseline_text = {r["sample_id"]: r["text"] for r in original}
                if {r["sample_id"]: r["text"] for r in samples} != baseline_text:
                    raise ValueError("paired text differs from baseline")
                for other in ("qwen", "jev"):
                    pairs.append(
                        {
                            "run": str(run_dir),
                            "training_seed": row["training_seed"],
                            "inference_repeat": row["repeat"],
                            "baseline_model": other,
                            "baseline_repeat": repeat,
                            **paired_accuracy(records, original, other + "_prediction"),
                        }
                    )
    capacities = confirmed_capacities(run_rows)
    write_csv(out / "runs.csv", run_rows)
    write_csv(out / "steady-60s-windows.csv", window_rows)
    write_csv(out / "paired-comparisons.csv", pairs)
    write_json(
        out / "audit.json",
        {
            "inputs": evidence,
            "capacity_points": capacities,
            "baseline_sha256": file_hash(baseline_path) if baseline_path else None,
            "note": "Repeated samples are not pooled. Capacity is deployment-specific and technical only. "
            "Training uncertainty and sample bootstrap uncertainty must be reported separately.",
        },
    )
    return run_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="*")
    parser.add_argument("--index", type=Path, action="append", default=[])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--pricing", type=Path, help="Actual instance/API pricing JSON; optional")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = list(args.runs)
    for path in args.index:
        index = json.loads(path.read_text(encoding="utf-8"))
        if index["state"] != "completed":
            parser.error("suite index must be completed; inspect interrupted runs separately")
        paths.extend(root / p for p in index["runs"])
    if not paths:
        parser.error("provide run directories or --index")
    pricing = json.loads(args.pricing.read_text(encoding="utf-8")) if args.pricing else None
    analyze(paths, args.out, args.baseline, pricing)
    print(f"Analysis saved: {args.out}")


if __name__ == "__main__":
    main()
