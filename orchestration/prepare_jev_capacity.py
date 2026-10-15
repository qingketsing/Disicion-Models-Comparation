"""Prepare Jev capacity runs with audited baseline reuse and conservative quota screening."""

import argparse
import math
from pathlib import Path

from decisionbench.analysis import audit_run, read_json
from decisionbench.artifacts import file_hash, write_json
from decisionbench.config import load_config
from decisionbench.suite import completed_entry, verify_bundle
from orchestration.prepare_qwen_capacity import create_capacity_bundle


class QuotaBudgetExceeded(ValueError):
    """Published quota is insufficient for the retry-amplified planning budget."""


def quota_screen(rates, retries, request_quota, token_quota, max_tokens_per_attempt):
    """Screen a four-attempt budget; this does not promise burst shaping or account quota."""
    values = [*rates, request_quota, token_quota, max_tokens_per_attempt]
    if not rates or any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("rates, quotas and measured token bound must be finite and positive")
    if retries != 3:
        raise ValueError("this Jev experiment requires three additional transport retries")
    multiplier = 1 + retries
    attempt_rps = max(rates) * multiplier
    token_rps = attempt_rps * max_tokens_per_attempt
    if attempt_rps > request_quota or token_rps > token_quota:
        raise QuotaBudgetExceeded("retry-amplified attempt or token budget exceeds the published quota")
    return dict(
        max_logical_rps=max(rates), max_attempt_multiplier=multiplier,
        projected_attempt_rps=attempt_rps, projected_token_rps=token_rps,
        published_request_rps=request_quota, published_token_rps=token_quota,
        observed_max_tokens_per_attempt=max_tokens_per_attempt,
        limitation="Conservative offered-rate screening using maximum observed same-input usage; "
        "not a tokenization guarantee, actual burst limiter or guaranteed account quota. "
        "Retry timing can align attempts; audit actual attempts and stop on API errors.",
    )


def create_jev_capacity_bundle(source_plan, root, out, rates, duration, repeats=3):
    original = read_json(source_plan)
    verify_bundle(original, root)
    state = read_json(root / "results/suites" / file_hash(source_plan) / "index.json")
    baselines, observed = [], []
    for job in original["jobs"]:
        if job["model"] != "jev" or job["block"] != "main":
            continue
        entry = state["jobs"].get(job["id"], {})
        if not completed_entry(entry, job, root):
            raise ValueError("all Jev main baselines must be completed before capacity preparation")
        cfg = load_config(root / job["config"])
        if cfg.adapter["kind"] != "jev":
            raise ValueError("capacity preparation requires the Jev adapter")
        manifest, rows, _, _, _, _ = audit_run(root / entry["run_dir"])
        for source, digest in manifest["source_files"].items():
            if file_hash(root / entry["run_dir"] / "source" / source) != digest:
                raise ValueError("baseline source snapshot changed")
        for row in rows:
            if row["input_tokens"] is None or row["output_tokens"] is None:
                raise ValueError("baseline usage missing; cannot screen token quota")
            observed.append(row["input_tokens"] + row["output_tokens"])
        baselines.append(cfg)
    if len(baselines) != 3:
        raise ValueError("exactly three audited Jev main repeats are required")
    cfg = baselines[0]
    screening = quota_screen(
        rates, cfg.network_retries, cfg.environment["api_quota_rps"],
        cfg.environment["api_quota_tokens_per_second"], max(observed),
    )
    if duration not in {120, 300} or repeats != 3:
        raise ValueError("Jev capacity requires 120/300-second runs and three repeats")
    # Existing helper preserves every baseline byte, deployment setting and completed entry.
    target = create_capacity_bundle(
        source_plan, root, out, rates, duration, repeats, model_name="jev"
    )
    plan = read_json(target)
    screening["planned_new_api_attempts_upper_bound"] = sum(
        j["api_requests_upper_bound"] for j in plan["jobs"] if j["block"] == "load"
    )
    # Supplementary evidence never changes the frozen plan or its hash.
    write_json(out / "quota-screening.json", screening)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rates", type=float, nargs="+", required=True)
    parser.add_argument("--duration", type=float, required=True)
    args = parser.parse_args()
    print(create_jev_capacity_bundle(
        args.source_plan.resolve(), Path.cwd(), args.out.resolve(), args.rates, args.duration
    ))


if __name__ == "__main__":
    main()
