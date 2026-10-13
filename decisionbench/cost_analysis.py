"""Batch offline pricing and explicit, user-validated monthly capacity scenarios."""

import argparse
from pathlib import Path

from decisionbench.analysis import audit_run, read_json, write_csv
from decisionbench.artifacts import file_hash, write_json
from decisionbench.metrics import monthly_tco, request_cost
from decisionbench.suite import completed_entry, verify_bundle


def price_suite(plan_path, root, pricing, out, scenarios=None, max_slo_qps=None):
    plan = read_json(plan_path)
    verify_bundle(plan, root)
    state = read_json(root / "results/suites" / file_hash(plan_path) / "index.json")
    if out.exists():
        raise ValueError("cost report exists; choose a new version directory")
    costs, api_total, api_samples = [], 0, 0
    usage_complete = True
    # Validate all prices before writing any result file.
    for prices in pricing.values():
        request_cost([], 0, prices, 500)
        for field in ("price_source", "price_date"):
            if not prices.get(field) or "TODO" in str(prices[field]).upper():
                raise ValueError(f"fill actual pricing metadata: {field}")
    if len({p["currency"] for p in pricing.values()}) != 1:
        raise ValueError("convert prices to one currency using the same exchange-rate date")
    updated = []
    for job in plan["jobs"]:
        entry = state["jobs"].get(job["id"], {})
        if not completed_entry(entry, job, root) or job["model"] not in pricing:
            continue
        directory = root / entry["run_dir"]
        manifest, records, _, _, _, _ = audit_run(directory)
        prices = pricing[job["model"]]
        kind = manifest["config"]["adapter"]["kind"]
        if (
            kind == "jev"
            and prices["billing"] != "api"
            or kind == "qwen"
            and prices["billing"] != "instance"
        ):
            raise ValueError("model billing type does not match its deployment")
        cost = request_cost(records, manifest["elapsed_s"], prices, manifest["config"]["slo_ms"])
        costs.append(
            {
                "job": job["id"],
                "model": job["model"],
                "block": job["block"],
                "synthetic": manifest["synthetic"],
                "currency": cost["currency"],
                "usage_complete": cost["usage_complete"],
                "total_measured_cost": cost["total_measured_cost"],
                "cost_per_million_successful": cost["cost_per_million_successful"],
                "cost_per_million_slo_valid": cost["cost_per_million_slo_valid"],
            }
        )
        updated.append((directory, cost))
        if job["block"] == "main" and prices["billing"] == "api":
            api_total += cost["total_measured_cost"]
            api_samples += len(records)
            usage_complete = usage_complete and cost["usage_complete"]
    if not costs:
        raise ValueError("no completed runs match the supplied model prices")
    tco = []
    if scenarios is not None:
        instances = [p for p in pricing.values() if p["billing"] == "instance"]
        apis = [p for p in pricing.values() if p["billing"] == "api"]
        if len(instances) != 1 or len(apis) != 1 or not api_samples or max_slo_qps is None:
            raise ValueError(
                "monthly comparison requires one instance price, main API quality runs, "
                "and --max-slo-qps from independently validated capacity"
            )
        for scenario in scenarios["scenarios"]:
            estimate = monthly_tco(
                scenario["monthly_requests"],
                scenario["peak_rps"],
                max_slo_qps,
                instances[0]["instance_price_per_hour"],
                hours=scenarios["hours"],
                utilization=scenarios["utilization"],
                training_cost=scenarios["training_cost"],
                maintenance_cost=scenarios["maintenance_cost"],
            )
            tco.append(
                {
                    "scenario": scenario["name"],
                    "monthly_requests": scenario["monthly_requests"],
                    "peak_rps": scenario["peak_rps"],
                    "currency": instances[0]["currency"],
                    "instance_replicas": estimate["replicas"],
                    "instance_monthly_tco": estimate["monthly_tco"],
                    "api_monthly_estimate": api_total / api_samples * scenario["monthly_requests"],
                    "api_usage_complete": usage_complete,
                    "max_slo_qps_user_supplied": max_slo_qps,
                    "api_peak_quota_validated": False,
                }
            )
    out.mkdir(parents=True)
    for directory, cost in updated:
        write_json(directory / "cost.json", cost)
    write_json(out / "pricing.json", pricing)
    write_csv(out / "request-costs.csv", costs)
    write_csv(out / "monthly-tco.csv", tco)
    write_json(
        out / "assumptions.json",
        {
            "plan_sha256": file_hash(plan_path),
            "scenarios": scenarios,
            "max_slo_qps": max_slo_qps,
            "note": "Capacity supplied by the experimenter; API peak quota not automatically attested. "
            "API monthly price assumes the main quality workload's token distribution. "
            "Missing usage produces a lower bound; warmup and idle excluded from run costs.",
        },
    )
    return costs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--pricing", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path)
    parser.add_argument("--max-slo-qps", type=float)
    args = parser.parse_args()
    try:
        costs = price_suite(
            args.plan.resolve(),
            args.root.resolve(),
            read_json(args.pricing),
            args.out.resolve(),
            read_json(args.scenarios) if args.scenarios else None,
            args.max_slo_qps,
        )
        print(f"Repriced {len(costs)} runs; no model requests sent: {args.out}")
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
