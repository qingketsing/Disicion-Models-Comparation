"""Offline recomputation, matched error cases, CSV tables and optional figures."""

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json
from decisionbench.config import RunConfig
from decisionbench.datasets import load_catalog, load_samples, read_jsonl
from decisionbench.metrics import request_cost, summarize
from decisionbench.suite import completed_entry, verify_bundle


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def independent_quality(records, labels):
    """Compute F1 directly from a confusion table, separate from harness aggregation."""
    matrix = Counter(
        (r["expected_label"], r["prediction"] if r["status"] == "ok" else "__failure__")
        for r in records
    )
    total = len(records)
    f1s, supported = [], []
    correct = 0
    for label in labels:
        actual = sum(n for (truth, prediction), n in matrix.items() if truth == label)
        predicted = sum(n for (truth, prediction), n in matrix.items() if prediction == label)
        tp = matrix[label, label]
        correct += tp
        f1 = 2 * tp / (actual + predicted) if actual + predicted else 0
        f1s.append(f1)
        if actual:
            supported.append(f1)
    return {
        "accuracy": correct / total if total else None,
        "macro_f1": statistics.mean(f1s) if f1s else None,
        "macro_f1_supported_classes": statistics.mean(supported) if supported else None,
    }


def wilson(correct, total):
    if not total:
        return None, None
    z = 1.959963984540054
    p = correct / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    width = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return center - width, center + width


def paired_bootstrap(differences, seed=42, draws=2000):
    """Paired accuracy difference CI; repeated calls on one sample are not independent."""
    rng = random.Random(seed)
    n = len(differences)
    if not n:
        raise ValueError("no samples for paired comparison")
    estimates = sorted(sum(rng.choices(differences, k=n)) / n for _ in range(draws))
    return (
        statistics.mean(differences),
        estimates[int(draws * 0.025)],
        estimates[int(draws * 0.975)],
    )


def audit_run(directory):
    manifest = read_json(directory / "manifest.json")
    if manifest["state"] != "completed":
        raise ValueError("analysis requires completed runs")
    dataset = directory / "inputs/dataset.jsonl"
    catalog_path = directory / "inputs/catalog-0.json"
    if file_hash(dataset) != manifest["dataset_sha256"]:
        raise ValueError("frozen run dataset hash mismatch")
    if file_hash(catalog_path) != manifest["catalog_sha256"][0]:
        raise ValueError("frozen run catalog hash mismatch")
    if file_hash(directory / "inputs/config.yaml") != manifest["config_sha256"]:
        raise ValueError("frozen run config hash mismatch")
    catalog = load_catalog(catalog_path)
    samples = load_samples(dataset, [catalog])
    sample_map = {s.sample_id: s for s in samples}
    rows = read_jsonl(directory / "requests.jsonl")
    config = RunConfig(**manifest["config"])
    expected_count = (
        len(samples)
        if config.mode == "quality"
        else math.ceil(config.duration_s * config.offered_rps)
    )
    if len(rows) != expected_count or len({r["request_id"] for r in rows}) != len(rows):
        raise ValueError("request log is incomplete or contains duplicate request IDs")
    if config.mode == "quality" and (
        len({r["sample_id"] for r in rows}) != len(samples)
        or {r["sample_id"] for r in rows} != set(sample_map)
    ):
        raise ValueError("quality run does not cover every sample exactly once")
    allowed_statuses = {
        "ok",
        "timeout",
        "http_error",
        "network_error",
        "invalid_output",
        "adapter_error",
        "client_overload",
    }
    for row in rows:
        sample = sample_map.get(row["sample_id"])
        if sample is None or row["expected_label"] != sample.label:
            raise ValueError("request ground truth does not match frozen dataset")
        if row["status"] not in allowed_statuses:
            raise ValueError("unfinished or unknown request status")
        if row["status"] == "ok" and row["prediction"] not in catalog.labels:
            raise ValueError("successful prediction is outside the catalog")
    recomputed = summarize(rows, config, manifest["elapsed_s"], catalog.labels)
    independent = independent_quality(rows, catalog.labels)
    stored = read_json(directory / "summary.json")
    for key, value in independent.items():
        if value is None or not math.isclose(value, stored["quality"][key], abs_tol=1e-12):
            raise ValueError(f"stored quality metric does not independently reproduce: {key}")
    for key in ("success_rate", "goodput_qps", "correct_goodput_qps"):
        if not math.isclose(recomputed[key], stored[key], abs_tol=1e-12):
            raise ValueError(f"stored performance metric does not reproduce: {key}")
    cost_file = directory / "cost.json"
    cost = (
        request_cost(rows, manifest["elapsed_s"], read_json(cost_file)["pricing"], config.slo_ms)
        if cost_file.exists()
        else recomputed["cost"]
    )
    return manifest, rows, samples, recomputed, independent, cost


def analyze(plan_path, root, out, plots=False):
    plan = read_json(plan_path)
    verify_bundle(plan, root)
    state_path = root / "results/suites" / file_hash(plan_path) / "index.json"
    state = read_json(state_path)
    if out.exists():
        raise ValueError("report directory exists; use a new version to preserve previous analyses")
    out.mkdir(parents=True)
    tables, audits, runs = [], [], []
    for job in plan["jobs"]:
        entry = state["jobs"].get(job["id"], {})
        if not completed_entry(entry, job, root):
            continue
        directory = root / entry["run_dir"]
        manifest, records, samples, summary, independent, cost = audit_run(directory)
        audits.append(
            {
                "job": job["id"],
                "run": entry["run_dir"],
                "state": "passed",
                "independent_quality": independent,
                "requests_sha256": file_hash(directory / "requests.jsonl"),
            }
        )
        correct = sum(
            r["status"] == "ok" and r["prediction"] == r["expected_label"] for r in records
        )
        lo, hi = wilson(correct, len(records))
        row = {
            "job": job["id"],
            "run": entry["run_dir"],
            "block": job["block"],
            "model": job["model"],
            "variant": job["variant"],
            "seed": job["seed"],
            "repeat": job["repeat"],
            "synthetic": manifest["synthetic"],
            "dataset_sha256": manifest["dataset_sha256"],
            "catalog_sha256": manifest["catalog_sha256"][0],
            "requests": len(records),
            **independent,
            "accuracy_ci95_low": lo if summary["mode"] == "quality" else None,
            "accuracy_ci95_high": hi if summary["mode"] == "quality" else None,
            "success_rate": summary["success_rate"],
            "p50_ms": summary["latency_attempted"]["p50_ms"],
            "p95_ms": summary["latency_attempted"]["p95_ms"],
            "p99_ms": summary["latency_attempted"]["p99_ms"],
            "goodput_qps": summary["goodput_qps"],
            "correct_goodput_qps": summary["correct_goodput_qps"],
            "client_measurement_valid": summary["client_measurement_valid"],
            "slo_capacity_candidate": summary["slo_capacity_candidate"],
            "offered_rps": summary.get("offered_rps"),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in records),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in records),
            "currency": cost.get("currency"),
            "usage_complete": cost.get("usage_complete"),
            "total_measured_cost": cost.get("total_measured_cost"),
            "cost_per_million_successful": cost.get("cost_per_million_successful"),
            "cost_per_million_slo_valid": cost.get("cost_per_million_slo_valid"),
            "cost_source": "cost.json" if (directory / "cost.json").exists() else "run_config",
        }
        tables.append(row)
        runs.append((job, records, samples))
        write_csv(
            out / f"{job['id']}-per-class.csv",
            [
                {"label": label, **metrics}
                for label, metrics in summary["quality"]["per_class"].items()
            ],
        )
        write_csv(out / f"{job['id']}-confusion.csv", summary["quality"]["confusion"])
    if not tables:
        raise ValueError("no completed runs to analyze")
    write_csv(out / "runs.csv", tables)
    groups = defaultdict(list)
    for row in tables:
        groups[row["block"], row["model"], row["variant"], row["synthetic"]].append(row)
    aggregated = []
    for (block, model, variant, synthetic), rows in groups.items():
        item = {
            "block": block,
            "model": model,
            "variant": variant,
            "synthetic": synthetic,
            "runs": len(rows),
        }
        for key in (
            "accuracy",
            "macro_f1_supported_classes",
            "p95_ms",
            "goodput_qps",
            "correct_goodput_qps",
            "success_rate",
        ):
            values = [r[key] for r in rows if r[key] is not None]
            item[key + "_mean"] = statistics.mean(values) if values else None
            item[key + "_sd"] = statistics.stdev(values) if len(values) > 1 else None
            item[key + "_min"] = min(values) if values else None
            item[key + "_max"] = max(values) if values else None
        aggregated.append(item)
    write_csv(out / "groups.csv", aggregated)
    pairs, cases = [], []
    paired_groups = defaultdict(list)
    for job, records, samples in runs:
        if job["block"] != "load":
            paired_groups[
                job["block"],
                job["variant"],
                job["seed"],
                job["repeat"],
                job["dataset_sha256"],
                job["catalog_sha256"],
            ].append((job, records, samples))
    for group in paired_groups.values():
        if len(group) != 2:
            continue
        left, right = sorted(group, key=lambda item: item[0]["model"])
        left_rows = {r["sample_id"]: r for r in left[1]}
        right_rows = {r["sample_id"]: r for r in right[1]}
        if set(left_rows) != set(right_rows):
            raise ValueError("paired runs cover different samples")
        texts = {s.sample_id: s.text for s in left[2]}
        differences, outcomes = [], Counter()
        for sample_id in sorted(left_rows):
            a, b = left_rows[sample_id], right_rows[sample_id]
            ac = a["status"] == "ok" and a["prediction"] == a["expected_label"]
            bc = b["status"] == "ok" and b["prediction"] == b["expected_label"]
            outcome = (
                "both_correct"
                if ac and bc
                else "left_only"
                if ac
                else "right_only"
                if bc
                else "both_wrong"
            )
            differences.append(int(bc) - int(ac))
            outcomes[outcome] += 1
            cases.append(
                {
                    "left_job": left[0]["id"],
                    "right_job": right[0]["id"],
                    "sample_id": sample_id,
                    "text": texts[sample_id],
                    "expected_label": a["expected_label"],
                    "outcome": outcome,
                    "left_prediction": a["prediction"],
                    "left_status": a["status"],
                    "right_prediction": b["prediction"],
                    "right_status": b["status"],
                }
            )
        difference, lo, hi = paired_bootstrap(differences)
        pairs.append(
            {
                "left_job": left[0]["id"],
                "right_job": right[0]["id"],
                "accuracy_difference_right_minus_left": difference,
                "paired_ci95_low": lo,
                "paired_ci95_high": hi,
                **{
                    name: outcomes[name]
                    for name in ("both_correct", "left_only", "right_only", "both_wrong")
                },
            }
        )
    write_csv(out / "paired-comparisons.csv", pairs)
    write_csv(out / "error-cases.csv", cases)
    write_json(out / "audit.json", {"plan_sha256": file_hash(plan_path), "runs": audits})
    note = (
        "# 实验结果分析\n\n"
        f"已完成并复算 {len(tables)} / {len(plan['jobs'])} 个计划实验。\n\n"
        "- runs.csv：每次运行的质量、延迟、吞吐、用量和成本。\n"
        "- groups.csv：重复实验或类别抽样种子的均值、标准差和范围；不合并原始请求。\n"
        "- paired-comparisons.csv：相同样本/目录的两模型配对准确率差与 95% bootstrap 区间。\n"
        "- error-cases.csv：全部配对样本，可筛选 left_only、right_only、both_wrong 做人工分析。\n"
        "- audit.json：冻结输入检查与独立质量指标复算；属于确定性检查。\n\n"
        "类别规模比较使用 macro_f1_supported_classes；完整目录 Macro-F1 仍保留在 runs.csv。\n"
        "准确率 Wilson 区间描述固定模型在样本上的不确定性；重复调用相同样本不增加独立样本量。\n"
        "配对区间仅在同一目录内比较模型；候选类别数量跨目录比较需查看同种子的差值。\n"
        "容量候选尚需独立质量要求、较长稳态和重复验证。成本未覆盖预热、空闲或租赁整段时长。\n"
        "synthetic=true 的数据仅用于工具验证，不作为真实模型结论。\n"
    )
    (out / "REPORT.md").write_text(note, encoding="utf-8")
    if plots:
        plot_tables(tables, out)
    return tables


def plot_tables(tables, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for block, metric, xlabel in (
        ("load", "p95_ms", "Offered requests/s"),
        ("load", "correct_goodput_qps", "Offered requests/s"),
        ("scale", "accuracy", "Candidate labels"),
        ("scale", "p95_ms", "Candidate labels"),
    ):
        grouped = defaultdict(list)
        for row in tables:
            if row["block"] == block and row[metric] is not None:
                x = row["offered_rps"] if block == "load" else int(row["variant"][1:])
                grouped[row["model"], x].append(row[metric])
        if not grouped:
            continue
        fig, ax = plt.subplots(figsize=(6, 4))
        for model in sorted({key[0] for key in grouped}):
            xs = sorted(key[1] for key in grouped if key[0] == model)
            ys = [statistics.mean(grouped[model, x]) for x in xs]
            sd = [
                statistics.stdev(grouped[model, x]) if len(grouped[model, x]) > 1 else 0 for x in xs
            ]
            ax.errorbar(xs, ys, yerr=sd, marker="o", capsize=3, label=model)
        ax.set(xlabel=xlabel, ylabel=metric, title="Mean with ±1 SD across runs/seeds")
        ax.grid(alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / f"{block}-{metric}.png", dpi=200)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Offline suite analysis; no model calls")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    try:
        rows = analyze(args.plan.resolve(), args.root.resolve(), args.out.resolve(), args.plots)
        print(f"Analyzed {len(rows)} completed runs: {args.out}")
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
