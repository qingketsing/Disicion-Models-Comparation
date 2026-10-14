"""Freeze a Qwen load bundle with audited, explicitly cited existing quality baselines."""

import argparse
import copy
from pathlib import Path

import yaml

from decisionbench.analysis import audit_run, read_json
from decisionbench.artifacts import file_hash, write_json
from decisionbench.config import load_config
from decisionbench.suite import completed_entry, prepare, verify_bundle


def create_capacity_bundle(source_plan, root, out, rates, duration, repeats=3):
    original = read_json(source_plan)
    verify_bundle(original, root)
    if file_hash(source_plan.parent / "suite.yaml") != original["suite_sha256"]:
        raise ValueError("source suite specification changed after freeze")
    source_state = read_json(root / "results/suites" / file_hash(source_plan) / "index.json")
    spec = yaml.safe_load((source_plan.parent / "suite.yaml").read_text(encoding="utf-8"))
    model = copy.deepcopy(spec["models"]["qwen"])
    baselines = []
    for job in original["jobs"]:
        if job["block"] != "main" or job["model"] != "qwen":
            continue
        entry = source_state["jobs"].get(job["id"], {})
        if not completed_entry(entry, job, root):
            raise ValueError("all source Qwen main baselines must be completed")
        config = load_config(root / job["config"])
        if config.warmup != model.get("warmup", 0):
            raise ValueError("baseline warmup setting differs")
        _, _, _, summary, _, _ = audit_run(root / entry["run_dir"])
        if config.adapter != model["adapter"] or summary["success_rate"] < config.min_success_rate:
            raise ValueError("baseline adapter or successful output rate is inconsistent")
        environment = {k: v for k, v in config.environment.items() if k != "experiment"}
        if environment != model.get("environment", {}) or config.cost != model.get("cost", {}):
            raise ValueError("baseline environment or pricing differs")
        for key, value in spec.get("common", {}).items():
            if getattr(config, key) != value:
                raise ValueError(f"baseline measurement setting differs: {key}")
        baselines.append((copy.deepcopy(job), copy.deepcopy(entry)))
    if not baselines:
        raise ValueError("no complete Qwen main quality baselines")
    spec["models"] = {"qwen": model}
    spec["name"] = out.name
    for options in spec["blocks"].values():
        options["enabled"] = False
    spec["blocks"]["load"].update(enabled=True, rates=rates, duration_s=duration, repeats=repeats)
    config_path = root / "configs" / f"{out.name}.yaml"
    if config_path.exists():
        raise ValueError("capacity configuration already exists")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    target = prepare(config_path, root, out)
    plan = read_json(target)
    if plan["source_sha256"] != original["source_sha256"]:
        raise ValueError("source differs from baseline plan")
    for job in plan["jobs"]:
        if not any(
            job["dataset_sha256"] == b["dataset_sha256"]
            and job["catalog_sha256"] == b["catalog_sha256"]
            for b, _ in baselines
        ):
            raise ValueError("load inputs differ from existing main quality baseline")
    plan["jobs"] = [j for j, _ in baselines] + plan["jobs"]
    for baseline, _ in baselines:
        cfg = load_config(root / baseline["config"])
        for path in (cfg.dataset, cfg.catalog):
            plan["assets_sha256"][path] = file_hash(root / path)
    plan["baseline_reuse"] = {
        "source_plan": str(source_plan.relative_to(root)).replace("\\", "/"),
        "source_plan_sha256": file_hash(source_plan),
        "note": "Audited existing quality runs; no baseline requests sent again. "
        "Same source, adapter, deployment, measurement settings, dataset and catalog.",
        "runs": [{"job": j["id"], **e} for j, e in baselines],
    }
    write_json(target, plan)
    verify_bundle(plan, root)
    state_dir = root / "results/suites" / file_hash(target)
    state_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        state_dir / "index.json",
        {
            "plan_sha256": file_hash(target),
            "jobs": {j["id"]: e for j, e in baselines},
            "attempts": [],
            "imported_baseline_source_plan_sha256": file_hash(source_plan),
        },
    )
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rates", type=float, nargs="+", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    print(
        create_capacity_bundle(
            args.source_plan.resolve(),
            Path.cwd(),
            args.out.resolve(),
            args.rates,
            args.duration,
            args.repeats,
        )
    )


if __name__ == "__main__":
    main()
