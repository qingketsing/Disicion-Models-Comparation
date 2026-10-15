"""Audit Qwen-only completed suites, deduplicate reused baselines, and export evidence."""

import argparse
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from decisionbench.analysis import audit_run, paired_bootstrap, read_json, wilson, write_csv
from decisionbench.artifacts import file_hash, write_json
from decisionbench.metrics import percentile
from decisionbench.suite import completed_entry, verify_bundle


def load_runs(plans, root, model_name="qwen"):
    if model_name not in {"qwen", "jev"}:
        raise ValueError("report supports qwen or jev")
    found, seen = [], set()
    for path in plans:
        spec = read_json(path)
        verify_bundle(spec, root)
        state = read_json(root / "results/suites" / file_hash(path) / "index.json")
        for job in spec["jobs"]:
            if job["model"] != model_name:
                continue
            entry = state["jobs"].get(job["id"], {})
            if not completed_entry(entry, job, root):
                raise ValueError(f"unfinished {model_name} job: {job['id']}")
            if entry["run_dir"] in seen:
                continue
            directory = root / entry["run_dir"]
            manifest, rows, samples, summary, quality, cost = audit_run(directory)
            if (
                manifest["config"]["slo_ms"] != 500
                or manifest["config"]["max_scheduler_lag_ms"] != 20
            ):
                raise ValueError(
                    "this report's segment checks require 500ms SLO and 20ms scheduling"
                )
            for source, digest in manifest["source_files"].items():
                if file_hash(directory / "source" / source) != digest:
                    raise ValueError(f"run source snapshot differs: {source}")
            warmup = [
                json.loads(line)
                for line in (directory / "warmup_requests.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            if len(warmup) != manifest["config"]["warmup"]:
                raise ValueError("warmup request count differs")
            if manifest["synthetic"]:
                raise ValueError("synthetic runs cannot enter the actual model report")
            if manifest["config"]["adapter"]["kind"] != model_name:
                raise ValueError("run adapter differs from the report model")
            if model_name == "qwen" and manifest["config"]["environment"].get("structured_outputs_backend") != "guidance":
                raise ValueError("only fixed guidance v4 and derived suites are allowed")
            seen.add(entry["run_dir"])
            found.append(
                dict(
                    plan=path,
                    job=job,
                    entry=entry,
                    manifest=manifest,
                    rows=rows,
                    samples=samples,
                    summary=summary,
                    quality=quality,
                    cost=cost,
                    warmup=warmup,
                )
            )
    return found


def steady_windows(rows, duration, window=60):
    windows = []
    for start in range(0, int(duration), window):
        end = min(start + window, duration)
        part = [r for r in rows if start <= r["scheduled_s"] < end]
        attempted = [r for r in part if r["dispatch_s"] is not None]
        ok = sum(r["status"] == "ok" for r in part)
        valid = [r for r in part if r["status"] == "ok" and r["e2e_latency_ms"] <= 500]
        p95 = percentile([r["e2e_latency_ms"] for r in attempted], 95)
        max_lag = max((r["scheduler_lag_ms"] or 0 for r in part), default=0)
        success = ok / len(part) if part else 0
        windows.append(
            dict(
                start_s=start,
                end_s=end,
                requests=len(part),
                success_rate=success,
                p95_ms=p95,
                max_scheduler_lag_ms=max_lag,
                slo_valid_arrival_window_qps=len(valid) / (end - start),
                passed=success >= 0.99 and p95 is not None and p95 <= 500 and max_lag <= 20,
            )
        )
    return windows


def analyze(plans, root, out, model_name="qwen"):
    if out.exists():
        raise ValueError("use a new report directory")
    runs = load_runs(plans, root, model_name)
    currency = "cny" if model_name == "qwen" else "usd"
    for run in runs:
        if run['cost']['currency'].lower() != currency:
            raise ValueError("report currency differs from audited run pricing")
    out.mkdir(parents=True)
    tables, windows, audits, failures = [], [], [], []
    groups = defaultdict(list)
    for run in runs:
        j, m, s, q = run["job"], run["manifest"], run["summary"], run["quality"]
        rows = run["rows"]
        correct = sum(r["status"] == "ok" and r["prediction"] == r["expected_label"] for r in rows)
        lo, hi = wilson(correct, len(rows))
        item = dict(
            job=j["id"],
            run=run["entry"]["run_dir"],
            block=j["block"],
            variant=j["variant"],
            seed=j["seed"],
            repeat=j["repeat"],
            requests=len(rows),
            duration_s=m["config"]["duration_s"] if j["block"] == "load" else None,
            accuracy_ci95_low=lo,
            accuracy_ci95_high=hi,
            **q,
            success_rate=s["success_rate"],
            p50_ms=s["latency_attempted"]["p50_ms"],
            p95_ms=s["latency_attempted"]["p95_ms"],
            p99_ms=s["latency_attempted"]["p99_ms"],
            max_scheduler_lag_ms=s["scheduler_lag"]["max_ms"],
            offered_rps=s.get("offered_rps"),
            goodput_qps=s["goodput_qps"],
            correct_goodput_qps=s["correct_goodput_qps"],
            completed_throughput_qps=s["completed_throughput_qps"],
            slo_capacity_candidate=s["slo_capacity_candidate"],
            mean_input_tokens=statistics.mean(r["input_tokens"] or 0 for r in rows),
            mean_output_tokens=statistics.mean(r["output_tokens"] or 0 for r in rows),
            elapsed_s=m["elapsed_s"],
            warmup_requests=len(run["warmup"]),
        )
        item.update({
            f"total_measured_cost_{currency}": run["cost"]["total_measured_cost"],
            f"cost_per_million_successful_{currency}": run["cost"]["cost_per_million_successful"],
            f"cost_per_million_slo_valid_{currency}": run["cost"]["cost_per_million_slo_valid"],
            "usage_complete": run["cost"].get("usage_complete"),
        })
        if j["block"] == "load":
            segments = steady_windows(rows, item["duration_s"])
            for segment in segments:
                windows.append({"job": j["id"], "duration_s": item["duration_s"], **segment})
            item["all_60s_windows_passed"] = all(w["passed"] for w in segments)
        else:
            item["all_60s_windows_passed"] = None
        tables.append(item)
        groups[j["block"], j["variant"], item["duration_s"]].append(item)
        audits.append(
            dict(
                run=item["run"],
                requests_sha256=file_hash(root / item["run"] / "requests.jsonl"),
                source_snapshot_verified=True,
                independent_quality=q,
                states=Counter(r["status"] for r in rows),
            )
        )
        texts = {sample.sample_id: sample.text for sample in run["samples"]}
        for row in rows:
            if row["status"] != "ok":
                failures.append(
                    dict(
                        job=j["id"],
                        sample_id=row["sample_id"],
                        text=texts[row["sample_id"]],
                        status=row["status"],
                        expected=row["expected_label"],
                        prediction=row["prediction"],
                        input_tokens=row["input_tokens"],
                        output_tokens=row["output_tokens"],
                    )
                )
        if j["block"] == "main":
            write_csv(
                out / f"{j['id']}-per-class.csv",
                [{"label": label, **metric} for label, metric in s["quality"]["per_class"].items()],
            )
            write_csv(out / f"{j['id']}-confusion.csv", s["quality"]["confusion"])
    aggregate = []
    for (block, variant, duration), items in groups.items():
        agg = dict(block=block, variant=variant, duration_s=duration, runs=len(items))
        for key in [
            "accuracy",
            "macro_f1_supported_classes",
            "p95_ms",
            "goodput_qps",
            "correct_goodput_qps",
            "success_rate",
            f"cost_per_million_successful_{currency}",
        ]:
            values = [item[key] for item in items if item[key] is not None]
            agg.update(
                {
                    key + "_mean": statistics.mean(values),
                    key + "_sd": statistics.stdev(values) if len(values) > 1 else None,
                    key + "_min": min(values),
                    key + "_max": max(values),
                }
            )
        agg["all_repeats_candidate"] = (
            all(item["slo_capacity_candidate"] for item in items) if block == "load" else None
        )
        agg["all_windows_passed"] = (
            all(item["all_60s_windows_passed"] for item in items) if block == "load" else None
        )
        aggregate.append(agg)
    write_csv(out / "runs.csv", tables)
    write_csv(out / "groups.csv", aggregate)
    write_csv(out / "steady-60s-windows.csv", windows)
    write_csv(out / "failures.csv", failures)
    # Repetition disagreement is computed per unique test sample, never across 3N samples.
    mains = [r for r in runs if r["job"]["block"] == "main"]
    mains.sort(key=lambda r: r["job"]["repeat"])
    sample_maps = [{r["sample_id"]: r for r in run["rows"]} for run in mains]
    if not mains or any(set(x) != set(sample_maps[0]) for x in sample_maps):
        raise ValueError("main repetitions cover different samples")
    disagreement = []
    for sid in sorted(sample_maps[0]):
        predictions = [(x[sid]["status"], x[sid]["prediction"]) for x in sample_maps]
        if len(set(predictions)) > 1:
            disagreement.append(dict(sample_id=sid, predictions=json.dumps(predictions)))
    write_csv(out / "repeat-disagreements.csv", disagreement)
    # Select up to 40 unique errors: frequent confusion pairs then seeded remainder.
    first = mains[0]
    texts = {s.sample_id: s.text for s in first["samples"]}
    errors = [
        r for r in first["rows"] if r["status"] != "ok" or r["prediction"] != r["expected_label"]
    ]
    confusion = Counter((r["expected_label"], r["prediction"]) for r in errors)
    selected = []
    selected_ids = set()
    for pair, _ in confusion.most_common(20):
        row = next(r for r in errors if (r["expected_label"], r["prediction"]) == pair)
        selected.append(row)
        selected_ids.add(row["sample_id"])
    remaining = [r for r in errors if r["sample_id"] not in selected_ids]
    random.Random(42).shuffle(remaining)
    selected.extend(remaining[: max(0, 40 - len(selected))])
    cases = [
        dict(
            sample_id=r["sample_id"],
            text=texts[r["sample_id"]],
            expected=r["expected_label"],
            prediction=r["prediction"],
            status=r["status"],
            selection="top confusion pair or seeded remainder; first main repeat",
        )
        for r in selected
    ]
    write_csv(out / "selected-error-cases.csv", cases)
    # Within-seed paired comparisons isolate extra distractor labels.
    scales = defaultdict(dict)
    for run in runs:
        if run["job"]["block"] == "scale":
            scales[run["job"]["seed"]][int(run["job"]["variant"][1:])] = run
    paired = []
    for seed, by_size in scales.items():
        for small, large in [(10, 30), (30, 60), (10, 60)]:
            a, b = by_size[small], by_size[large]
            amap = {r["sample_id"]: r for r in a["rows"]}
            bmap = {r["sample_id"]: r for r in b["rows"]}
            assert set(amap) == set(bmap)
            diffs = [
                int(
                    bmap[sid]["status"] == "ok"
                    and bmap[sid]["prediction"] == bmap[sid]["expected_label"]
                )
                - int(
                    amap[sid]["status"] == "ok"
                    and amap[sid]["prediction"] == amap[sid]["expected_label"]
                )
                for sid in sorted(amap)
            ]
            diff, lo, hi = paired_bootstrap(diffs)
            paired.append(
                dict(
                    seed=seed,
                    smaller_k=small,
                    larger_k=large,
                    accuracy_larger_minus_smaller=diff,
                    ci95_low=lo,
                    ci95_high=hi,
                )
            )
    write_csv(out / "scale-paired-comparisons.csv", paired)
    formal = [
        g
        for g in aggregate
        if g["block"] == "load"
        and g["duration_s"] >= 300
        and g["runs"] >= 3
        and g["all_repeats_candidate"]
        and g["all_windows_passed"]
    ]
    capacity = max(formal, key=lambda g: float(g["variant"][3:])) if formal else None
    write_json(
        out / "audit.json",
        {
            "plans": [{"path": str(p.relative_to(root)), "sha256": file_hash(p)} for p in plans],
            "runs": audits,
            "main_unique_samples": len(sample_maps[0]),
            "repeat_disagreement_samples": len(disagreement),
            "technical_capacity_candidate": capacity,
            "semantic_accuracy_floor": None,
            "note": "Capacity attests legal output, latency and scheduling only; no business accuracy floor was supplied.",
            f"measurement_cost_{currency}": sum(r[f"total_measured_cost_{currency}"] for r in tables),
            "measured_seconds_including_drain": sum(r["elapsed_s"] for r in tables),
            "measured_requests": sum(r["requests"] for r in tables),
            "warmup_requests": sum(r["warmup_requests"] for r in tables),
        },
    )
    plot(tables, out)
    return tables


def plot(rows, out):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for block, metric in [
        ("load", "p95_ms"),
        ("load", "correct_goodput_qps"),
        ("scale", "accuracy"),
        ("scale", "p95_ms"),
    ]:
        fig, ax = plt.subplots(figsize=(7, 4))
        group = defaultdict(list)
        for row in rows:
            if row["block"] == block:
                x = row["offered_rps"] if block == "load" else int(row["variant"][1:])
                group[row["duration_s"], x].append(row[metric])
        for duration in sorted({k[0] for k in group}, key=lambda v: v or 0):
            xs = sorted(k[1] for k in group if k[0] == duration)
            ax.errorbar(
                xs,
                [statistics.mean(group[duration, x]) for x in xs],
                yerr=[
                    statistics.stdev(group[duration, x]) if len(group[duration, x]) > 1 else 0
                    for x in xs
                ],
                marker="o",
                capsize=3,
                label=f"{duration:g}s" if duration else "three catalog seeds",
            )
        if metric == "p95_ms" and block == "load":
            ax.axhline(500, color="red", linestyle="--", label="500ms SLO")
        ax.set(
            xlabel="Offered requests/s" if block == "load" else "Candidate labels", ylabel=metric
        )
        ax.grid(alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / f"{block}-{metric}.png", dpi=200)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd()
    rows = analyze([p.resolve() for p in args.plan], root, args.out.resolve())
    print(f"Audited {len(rows)} distinct completed Qwen runs")


if __name__ == "__main__":
    main()
