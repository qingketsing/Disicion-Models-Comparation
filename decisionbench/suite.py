"""Prepare portable experiment bundles and run them through the existing harness.

Preparation and run previews never construct an adapter or send HTTP requests.
"""

import argparse
import asyncio
import json
import math
import os
import random
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from decisionbench.artifacts import file_hash, write_json
from decisionbench.cli import run
from decisionbench.config import RunConfig, load_config
from decisionbench.datasets import load_catalog, load_samples, read_jsonl
from decisionbench.metrics import request_cost
from decisionbench.protocol import Catalog
from decisionbench.variants import scale_variants, write_catalog, write_samples

BLOCKS = ("checkpoint", "main", "load", "scale", "descriptions")


def save_state(path, value):
    temporary = path.with_suffix(".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def positive_int(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def relative(path, root):
    return path.resolve().relative_to(root.resolve()).as_posix()


def prepare(config_path: Path, root: Path, out: Path):
    spec = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    dataset_dir = root / spec["dataset_dir"]
    catalog = load_catalog(dataset_dir / "catalog.json")
    provenance_path = dataset_dir / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("descriptions_reviewed") is not True:
        raise ValueError("review category descriptions and regenerate the normalized dataset first")
    for filename, expected in provenance.get("normalized_sha256", {}).items():
        if file_hash(dataset_dir / filename) != expected:
            raise ValueError(f"normalized dataset changed after provenance freeze: {filename}")
    if not spec.get("models"):
        raise ValueError("at least one model is required")
    for name, model in spec["models"].items():
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
            raise ValueError(
                "model IDs must use lowercase ASCII letters, digits, hyphen or underscore"
            )
        if model["adapter"]["kind"] not in {"qwen", "jev", "mock"}:
            raise ValueError("suite supports qwen, jev and local mock verification")
        if any(k in model["adapter"] for k in ("api_key", "token", "password")):
            raise ValueError(
                "store API keys in environment variables, never in suite configuration"
            )
    cooldown = spec.get("cooldown_s", 30)
    if not isinstance(cooldown, (int, float)) or not math.isfinite(cooldown) or cooldown < 0:
        raise ValueError("cooldown_s must be finite and nonnegative")
    relative(out, root)  # Bundle paths remain portable when the repository is uploaded.
    if out.exists():
        raise ValueError("bundle already exists; choose a new version directory")
    # Validate all enabled source datasets before creating the output directory.
    sources = {}
    for block, options in spec["blocks"].items():
        if block not in BLOCKS:
            raise ValueError(f"unknown experiment block: {block}")
        if options.get("enabled", False):
            sources[block] = load_samples(dataset_dir / options["dataset"], [catalog])
            if block == "checkpoint" and len(sources[block]) != 300:
                raise ValueError("checkpoint must contain exactly 300 samples")
    out.mkdir(parents=True)
    assets = out / "assets"
    assets.mkdir()
    config_dir = out / "configs"
    config_dir.mkdir()
    shutil.copyfile(config_path, out / "suite.yaml")
    shutil.copyfile(provenance_path, assets / "provenance.json")
    write_catalog(assets / "catalog.json", catalog)
    jobs = []

    def add(block, rows, active_catalog, variant, seed, repeat, rate=None):
        dataset = assets / f"{block}-{variant}-seed{seed}.jsonl"
        catalog_path = assets / f"{block}-{variant}-seed{seed}-catalog.json"
        if not dataset.exists():
            write_samples(dataset, rows)
            write_catalog(catalog_path, active_catalog)
        for model_id, model in spec["models"].items():
            job_id = f"{block}-{variant}-seed{seed}-rep{repeat}-{model_id}"
            data = dict(spec.get("common", {}))
            data.update(
                name=job_id,
                mode="load" if block == "load" else "quality",
                dataset=relative(dataset, root),
                catalog=relative(catalog_path, root),
                adapter=model["adapter"],
                warmup=model.get("warmup", 0),
                seed=seed,
                cost=model.get("cost", {}),
                environment={
                    **model.get("environment", {}),
                    "experiment": {
                        "suite": spec["name"],
                        "block": block,
                        "variant": variant,
                        "seed": seed,
                        "repeat": repeat,
                        "model_id": model_id,
                    },
                },
            )
            if rate is not None:
                data.update(offered_rps=rate, duration_s=spec["blocks"][block]["duration_s"])
            config = RunConfig(**data)
            request_cost([], 0, config.cost, config.slo_ms)
            path = config_dir / f"{job_id}.yaml"
            path.write_text(yaml.safe_dump(asdict(config), sort_keys=False), encoding="utf-8")
            count = math.ceil(config.duration_s * rate) if rate else len(rows)
            jobs.append(
                {
                    "id": job_id,
                    "block": block,
                    "model": model_id,
                    "variant": variant,
                    "seed": seed,
                    "repeat": repeat,
                    "config": relative(path, root),
                    "measurement_requests": count,
                    "warmup_requests": config.warmup,
                    "config_sha256": file_hash(path),
                    "dataset_sha256": file_hash(dataset),
                    "catalog_sha256": file_hash(catalog_path),
                    "api_requests_upper_bound": count + config.warmup
                    if config.adapter["kind"] == "jev"
                    else 0,
                }
            )

    for block in BLOCKS:
        if block not in sources:
            continue
        options, rows = spec["blocks"][block], sources[block]
        if block == "scale":
            seeds = options["seeds"]
            if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int for s in seeds):
                raise ValueError("scale seeds must be unique integers")
            for seed in seeds:
                selected, catalogs, anchors = scale_variants(
                    rows, catalog, options["sizes"], seed, options["samples_per_anchor_class"]
                )
                write_json(assets / f"scale-seed{seed}-anchors.json", {"labels": anchors})
                for size, active in catalogs.items():
                    add(block, selected, active, f"k{size}", seed, 1)
        elif block == "descriptions":
            for variant, mapping_path in options["mappings"].items():
                if not variant.isascii() or not variant.replace("-", "").isalnum():
                    raise ValueError("description variant must be an ASCII alphanumeric ID")
                mapping = json.loads((root / mapping_path).read_text(encoding="utf-8"))
                if set(mapping) != set(catalog.labels) or not all(
                    isinstance(v, str) and v.strip() for v in mapping.values()
                ):
                    raise ValueError("description mapping must cover the exact frozen label set")
                for repeat in range(1, positive_int(options["repeats"], "repeats") + 1):
                    add(
                        block,
                        rows,
                        Catalog(
                            f"{catalog.version}-{variant}",
                            {label: mapping[label] for label in catalog.labels},
                        ),
                        variant,
                        42,
                        repeat,
                    )
        else:
            for repeat in range(1, positive_int(options["repeats"], "repeats") + 1):
                seed = 41 + repeat
                if block == "load":
                    rates = list(options["rates"])
                    if not rates or len(set(rates)) != len(rates):
                        raise ValueError("load rates must be nonempty and unique")
                    random.Random(seed).shuffle(rates)
                    for rate in rates:
                        add(block, rows, catalog, f"rps{rate}", seed, repeat, rate)
                else:
                    add(block, rows, catalog, "full", seed, repeat)
    if not jobs:
        raise ValueError("no enabled experiment blocks")
    write_json(
        out / "plan.json",
        {
            "schema_version": 1,
            "name": spec["name"],
            "cooldown_s": cooldown,
            "suite_sha256": file_hash(out / "suite.yaml"),
            "assets_sha256": {relative(p, root): file_hash(p) for p in sorted(assets.iterdir())},
            "source_sha256": {
                relative(p, root): file_hash(p)
                for folder in ("decisionbench", "scripts", "services")
                for p in sorted((root / folder).glob("*.py"))
            },
            "jobs": jobs,
            "note": "Prepared only; no real model requests have been sent.",
        },
    )
    return out / "plan.json"


def verify_bundle(plan, root):
    if len({j["id"] for j in plan["jobs"]}) != len(plan["jobs"]):
        raise ValueError("duplicate job IDs in plan")
    for path, expected in plan.get("source_sha256", {}).items():
        if file_hash(root / path) != expected:
            raise ValueError(f"source changed after suite preparation: {path}")
    for path, expected in plan["assets_sha256"].items():
        if file_hash(root / path) != expected:
            raise ValueError(f"frozen input modified: {path}")
    for job in plan["jobs"]:
        if file_hash(root / job["config"]) != job["config_sha256"]:
            raise ValueError(f"frozen configuration modified: {job['id']}")
        config = load_config(root / job["config"])
        expected = (
            math.ceil(config.duration_s * config.offered_rps)
            if config.mode == "load"
            else len(read_jsonl(root / config.dataset))
        )
        expected_api = expected + config.warmup if config.adapter["kind"] == "jev" else 0
        if (
            config.name != job["id"]
            or expected != job["measurement_requests"]
            or config.warmup != job["warmup_requests"]
            or expected_api != job["api_requests_upper_bound"]
            or file_hash(root / config.dataset) != job["dataset_sha256"]
            or file_hash(root / config.catalog) != job["catalog_sha256"]
        ):
            raise ValueError(f"plan metadata disagrees with frozen configuration: {job['id']}")


def completed_entry(entry, job, root):
    if entry.get("state") != "completed":
        return False
    directory = root / entry["run_dir"]
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["state"] != "completed" or manifest["config_sha256"] != job["config_sha256"]:
        raise ValueError("resume entry is inconsistent with the completed run")
    for name, expected in entry.get("result_sha256", {}).items():
        if file_hash(directory / name) != expected:
            raise ValueError(f"completed run modified after execution: {name}")
    return True


def execution_checks(config):
    kind = config.adapter["kind"]
    if kind == "mock":
        return
    required = ["network_path"]
    if kind == "qwen":
        required += [
            "worker_gpu",
            "model_revision",
            "inference_precision",
            "max_model_len",
            "prefix_cache",
        ]
        if config.environment.get("deployment") == "native":
            required += ["worker_environment_sha256", "vllm_version"]
        else:
            required += ["container_digest"]
    else:
        required += ["api_quota_rps"]
        key = config.adapter.get("api_key_env")
        if not key or not os.environ.get(key):
            raise ValueError("Jev API key environment variable is missing")
    for name in required:
        value = config.environment.get(name)
        if value is None or not str(value).strip() or "TODO" in str(value).upper():
            raise ValueError(f"fill model environment metadata before execution: {name}")
    if kind == "qwen" and config.environment["model_revision"] in {"main", "latest"}:
        raise ValueError("freeze an immutable model revision")
    if kind == "jev" and config.mode == "load":
        quota = config.environment["api_quota_rps"]
        if not isinstance(quota, (int, float)) or not math.isfinite(quota) or quota <= 0:
            raise ValueError("api_quota_rps must be finite and positive")
        if config.offered_rps > quota:
            raise ValueError("planned Jev RPS exceeds the configured API quota")


def require_quality_baseline(job, plan, state, root):
    for candidate in plan["jobs"]:
        if (
            candidate["block"] == "main"
            and candidate["model"] == job["model"]
            and candidate["dataset_sha256"] == job["dataset_sha256"]
            and candidate["catalog_sha256"] == job["catalog_sha256"]
        ):
            entry = state["jobs"].get(candidate["id"], {})
            if completed_entry(entry, candidate, root):
                directory = root / entry["run_dir"]
                summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
                config = load_config(root / job["config"])
                if summary["success_rate"] >= config.min_success_rate:
                    return
    raise ValueError(f"complete a main quality baseline before load testing: {job['model']}")


async def run_plan(
    plan_path, root, blocks, models, execute=False, max_api_requests=None, retry_failed=False
):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    verify_bundle(plan, root)
    known_models = {job["model"] for job in plan["jobs"]}
    if set(blocks) - set(BLOCKS) or set(models) - known_models:
        raise ValueError("unknown block or model filter")
    jobs = [
        j
        for j in plan["jobs"]
        if (not blocks or j["block"] in blocks) and (not models or j["model"] in models)
    ]
    if not jobs:
        raise ValueError("no jobs match the filters")
    state_dir = root / "results" / "suites" / file_hash(plan_path)
    state_path = state_dir / "index.json"
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {
            "plan_sha256": file_hash(plan_path),
            "jobs": {},
            "attempts": [],
        }
    )
    remaining = [j for j in jobs if not completed_entry(state["jobs"].get(j["id"], {}), j, root)]
    budget = sum(j["api_requests_upper_bound"] for j in remaining)
    preview = {
        "selected_runs": len(jobs),
        "remaining_runs": len(remaining),
        "api_requests_upper_bound_this_invocation": budget,
        "measurement_requests_remaining": sum(j["measurement_requests"] for j in remaining),
        "warmup_requests_remaining": sum(j["warmup_requests"] for j in remaining),
        "jobs": [j["id"] for j in remaining],
        "execute": execute,
        "index": str(state_path),
    }
    print(json.dumps(preview, indent=2))
    if not execute or not remaining:
        return preview
    if budget and (type(max_api_requests) is not int or max_api_requests < budget):
        raise ValueError(f"API budget must cover up to {budget} requests including warmup")
    # Entire selection is checked before the first request; failed attempts require explicit retry.
    for job in remaining:
        if job["id"] in state["jobs"] and not retry_failed:
            raise ValueError("unfinished attempt found; inspect logs before using --retry-failed")
        config = load_config(root / job["config"])
        execution_checks(config)
        if job["block"] == "load":
            require_quality_baseline(job, plan, state, root)
    state_dir.mkdir(parents=True, exist_ok=True)
    # A process lock prevents two controllers sending the same suite requests.
    lock_path = state_dir / "running.lock"
    with lock_path.open("x", encoding="utf-8") as lock:
        lock.write(str(os.getpid()))
    try:
        if state_path.exists() and json.loads(state_path.read_text(encoding="utf-8")) != state:
            raise ValueError("suite state changed during preflight; preview again before execution")
        for i, job in enumerate(remaining):
            entry = {
                "state": "running",
                "config_sha256": job["config_sha256"],
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            state["jobs"][job["id"]] = entry
            attempt = {"job": job["id"], **entry}
            state["attempts"].append(attempt)
            save_state(state_path, state)
            try:

                def created(output):
                    entry["run_dir"] = relative(output, root)
                    attempt.update(entry)
                    save_state(state_path, state)

                output = await run((root / job["config"]).resolve(), root, on_created=created)
                entry.update(state="completed", run_dir=relative(output, root))
                entry["result_sha256"] = {
                    name: file_hash(output / name)
                    for name in ("manifest.json", "requests.jsonl", "summary.json")
                }
            except BaseException as exc:
                entry.update(
                    state="interrupted"
                    if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError))
                    else "failed",
                    error_type=type(exc).__name__,
                )
                raise
            finally:
                entry["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                attempt.update(entry)
                save_state(state_path, state)
            if i + 1 < len(remaining):
                await asyncio.sleep(plan["cooldown_s"])
    finally:
        lock_path.unlink()
    return preview


def main():
    parser = argparse.ArgumentParser(description="Prepare and execute Qwen/Jev experiment suites")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("prepare", help="Freeze inputs/configs; sends no requests")
    command.add_argument("-c", "--config", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True)
    command.add_argument("--root", type=Path, default=Path.cwd())
    command = sub.add_parser("run", help="Preview by default; --execute sends model requests")
    command.add_argument("--plan", type=Path, required=True)
    command.add_argument("--root", type=Path, default=Path.cwd())
    command.add_argument("--block", action="append", choices=BLOCKS, default=[])
    command.add_argument("--model", action="append", default=[])
    command.add_argument("--execute", action="store_true")
    command.add_argument("--max-api-requests", type=int)
    command.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.config.resolve(), args.root.resolve(), args.out.resolve()))
        else:
            asyncio.run(
                run_plan(
                    args.plan.resolve(),
                    args.root.resolve(),
                    args.block,
                    args.model,
                    args.execute,
                    args.max_api_requests,
                    args.retry_failed,
                )
            )
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
