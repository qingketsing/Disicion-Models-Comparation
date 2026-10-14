"""Run bounded adaptive Qwen load extension and independent 300-second confirmation."""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from decisionbench.analysis import audit_run, read_json
from decisionbench.artifacts import file_hash, write_json
from decisionbench.suite import completed_entry, verify_bundle
from orchestration.prepare_qwen_capacity import create_capacity_bundle

ROOT = Path.cwd()
PILOT = ROOT / "experiments/massive-qwen-guidance-pilot-v4/plan.json"
STATUS = ROOT / "results/execution-20261014/qwen-capacity-status.json"


def rate_results(plan):
    spec = read_json(plan)
    verify_bundle(spec, ROOT)
    state = read_json(ROOT / "results/suites" / file_hash(plan) / "index.json")
    groups = defaultdict(list)
    for job in spec["jobs"]:
        if job["block"] != "load" or job["model"] != "qwen":
            continue
        entry = state["jobs"].get(job["id"], {})
        if not completed_entry(entry, job, ROOT):
            raise ValueError("load stage incomplete")
        _, _, _, summary, _, _ = audit_run(ROOT / entry["run_dir"])
        groups[summary["offered_rps"]].append(summary)
    return {
        rate: {
            "runs": len(rows),
            "all_repeats_pass": len(rows) == 3 and all(r["slo_capacity_candidate"] for r in rows),
            "p95_max_ms": max(r["latency_attempted"]["p95_ms"] for r in rows),
            "success_min": min(r["success_rate"] for r in rows),
            "lag_max_ms": max(r["scheduler_lag"]["max_ms"] for r in rows),
        }
        for rate, rows in groups.items()
    }


def execute_bundle(name, rates, duration, evidence):
    target = create_capacity_bundle(PILOT, ROOT, ROOT / "experiments" / name, rates, duration, 3)
    relative = str(target.relative_to(ROOT))
    evidence["plans"].append(relative)
    evidence["active_plan"] = relative
    write_json(STATUS, evidence)
    result = subprocess.run(
        [
            sys.executable,
            "orchestration/stage_watchdog.py",
            "--model",
            "qwen",
            "--block",
            "load",
            "--plan",
            relative,
            "--stop-invalid",
            "--log-prefix",
            f"results/execution-20261014/{name}",
        ]
    )
    if result.returncode:
        raise RuntimeError("Qwen load Controller stopped; inspect watchdog evidence")
    results = rate_results(target)
    evidence["stages"].append({"plan": relative, "duration_s": duration, "rates": results})
    write_json(STATUS, evidence)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-suffix", default="")
    args = parser.parse_args()
    suffix = args.attempt_suffix
    if suffix and (not suffix.isascii() or not suffix.replace("-", "").isalnum()):
        raise ValueError("attempt suffix must contain ASCII letters, digits or hyphens")
    suffix = f"-{suffix}" if suffix else ""
    if STATUS.exists():
        raise ValueError("capacity driver already exists; inspect before resuming")
    evidence = {
        "state": "waiting_for_pilot",
        "pid": os.getpid(),
        "jev_requests": 0,
        "attempt_suffix": args.attempt_suffix,
        "plans": [str(PILOT.relative_to(ROOT))],
        "stages": [],
        "extension_policy": "If all three 8-RPS pilot repeats pass, test 16/32, "
        "then double up to 256 RPS until a tested rate fails. Three 120s repeats each. "
        "Confirm highest passing tested rate and nearest higher failing tested rate "
        "with three 300s repeats. No business semantic accuracy floor was supplied.",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(STATUS, evidence)
    try:
        for _ in range(1080):
            try:
                status = read_json(ROOT / "results/execution-20261014/qwen-v4-status.json")
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(1)
                continue
            if status.get("state") == "completed":
                break
            process = Path("/proc/20426/stat")
            if not process.exists() or process.read_text().split()[2] == "Z":
                raise RuntimeError("pilot driver exited without successful completion")
            time.sleep(10)
        else:
            raise RuntimeError("pilot did not complete within three hours")
        evidence["state"] = "running"
        rates = rate_results(PILOT)
        evidence["stages"].append(
            {"plan": str(PILOT.relative_to(ROOT)), "duration_s": 120, "rates": rates}
        )
        write_json(STATUS, evidence)
        if rates[8]["all_repeats_pass"]:
            rates.update(
                execute_bundle(
                    f"massive-qwen-guidance-extended16-32-v4{suffix}", [16, 32], 120, evidence
                )
            )
            next_rate = 64
            while rates[next_rate / 2]["all_repeats_pass"] and next_rate <= 256:
                rates.update(
                    execute_bundle(
                        f"massive-qwen-guidance-extended{next_rate}-v4{suffix}",
                        [next_rate], 120, evidence
                    )
                )
                next_rate *= 2
        passing = [rate for rate, value in rates.items() if value["all_repeats_pass"]]
        if not passing:
            raise RuntimeError("no pilot rate passed the frozen client and latency requirements")
        candidate = max(passing)
        failing = [
            rate
            for rate, value in rates.items()
            if rate > candidate and not value["all_repeats_pass"]
        ]
        formal_rates = [candidate] + ([min(failing)] if failing else [])
        evidence["selected_formal_rates"] = formal_rates
        execute_bundle(f"massive-qwen-guidance-formal-v4{suffix}", formal_rates, 300, evidence)
        evidence.update(
            state="completed", finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
        write_json(STATUS, evidence)
    except BaseException as exc:
        evidence.update(
            state="failed",
            error_type=type(exc).__name__,
            finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        write_json(STATUS, evidence)
        raise


if __name__ == "__main__":
    main()
