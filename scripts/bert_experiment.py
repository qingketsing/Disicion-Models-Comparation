"""Prepare, train and evaluate BERT from a portable frozen experiment plan."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from decisionbench.artifacts import file_hash, write_json
from decisionbench.cli import run
from decisionbench.config import RunConfig
from decisionbench.datasets import load_catalog
from scripts.prepare_datasets import MASSIVE_URL, download
from services.common import catalog_signature
from services.train_bert import parse_args as parse_training_args

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577"


def relative_path(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("plan paths must be relative to the repository root")
    return path.as_posix()


def validate_spec(spec):
    training_args = [
        "--train",
        "unused",
        "--validation",
        "unused",
        "--catalog",
        "unused",
        "--out",
        "unused",
        "--revision",
        "a" * 40,
    ]
    for key, value in spec["training"].items():
        if key in {
            "train",
            "validation",
            "catalog",
            "out",
            "revision",
            "base_model",
            "seed",
            "resume",
            "max_steps",
        }:
            raise ValueError(f"{key} is not a training override in a formal plan")
        training_args += ["--" + key.replace("_", "-"), str(value)]
    parse_training_args(training_args)
    if not isinstance(spec.get("seeds"), list) or not spec["seeds"]:
        raise ValueError("at least one training seed is required")
    if any(type(seed) is not int for seed in spec["seeds"]):
        raise ValueError("training seeds must be integers")
    if len(set(spec["seeds"])) != len(spec["seeds"]):
        raise ValueError("training seeds must be unique")
    for name in ("data_dir", "model_dir", "output_dir"):
        relative_path(spec[name])
    if not re.fullmatch(r"[A-Za-z0-9_-]+", spec["name"]):
        raise ValueError("name must contain only letters, digits, underscores and hyphens")
    measurement = spec["measurement"]
    if type(measurement["repeats"]) is not int or measurement["repeats"] < 3:
        raise ValueError("at least three measurement repeats are required")
    if not math.isfinite(measurement["cooldown_s"]) or measurement["cooldown_s"] < 0:
        raise ValueError("cooldown must be finite and nonnegative")
    if not measurement["pilot_rps"]:
        raise ValueError("pilot RPS list must not be empty")
    for rate in measurement["pilot_rps"]:
        for duration in (measurement["pilot_duration_s"], measurement["formal_duration_s"]):
            RunConfig(
                name="preflight",
                mode="load",
                dataset="data",
                catalog="catalog",
                adapter={"kind": "bert"},
                offered_rps=rate,
                duration_s=duration,
                **{
                    k: measurement[k]
                    for k in (
                        "warmup",
                        "timeout_s",
                        "slo_ms",
                        "min_success_rate",
                        "max_scheduler_lag_ms",
                        "max_concurrency",
                    )
                },
            )


def source_hashes():
    paths = [
        p
        for folder in ("decisionbench", "services", "scripts")
        for p in (ROOT / folder).glob("*.py")
    ]
    paths += [
        ROOT / name
        for name in (
            "requirements-bert.txt",
            "requirements-bert.lock.txt",
            "pyproject.toml",
        )
    ]
    return {p.relative_to(ROOT).as_posix(): source_digest(p) for p in sorted(paths)}


def source_digest(path):
    # Git checkouts on Windows and Linux may use different line endings.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def prepare(args):
    spec = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    validate_spec(spec)
    if args.out.exists():
        raise ValueError("plan already exists; use a new plan path")
    from huggingface_hub import HfApi

    resolved = HfApi().model_info(spec["base_model"], revision=spec["revision"]).sha
    if not resolved or not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise ValueError("could not resolve an immutable model revision")
    source = args.source or ROOT / "data/raw/amazon-massive-dataset-1.1.tar.gz"
    if not source.exists():
        if args.source:
            raise FileNotFoundError(source)
        download(MASSIVE_URL, source)
    if file_hash(source) != SOURCE_SHA256:
        raise ValueError("publisher MASSIVE 1.1 archive hash differs from PR #2")
    data_dir = ROOT / spec["data_dir"]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.prepare_datasets",
            "--name",
            "massive",
            "--source",
            str(source.resolve()),
            "--locale",
            "en-US",
            "--seed",
            "42",
            "--descriptions",
            "reports/experiment-results-20261015/data-provenance/massive-ai-reviewed-v1.json",
            "--out",
            str(data_dir),
        ],
        check=True,
        cwd=ROOT,
    )
    # Use an explicit new version, not an inferred historical catalog version.
    catalog_file = data_dir / "catalog.json"
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    catalog["version"] = spec["name"] + "-catalog"
    write_json(catalog_file, catalog)
    provenance_path = data_dir / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance.update(
        description_reviewer="ai",
        split_policy="MASSIVE native splits; no deduplication",
        description_note="PR #2 AI-reviewed mapping; not human-reviewed",
        catalog_note="New BERT experiment version; historical catalog bytes not restored",
    )
    provenance["normalized_sha256"] = {
        p.name: file_hash(p) for p in sorted(data_dir.glob("*.json*")) if p != provenance_path
    }
    write_json(provenance_path, provenance)
    spec["requested_revision"] = spec["revision"]
    spec["revision"] = resolved
    spec.update(
        schema_version=1,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        data_sha256={
            p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(data_dir.glob("*.json*"))
        },
        source_sha256=source_hashes(),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, spec)
    write_json(args.out.with_suffix(".sha256.json"), {"plan_sha256": file_hash(args.out)})
    print(f"Frozen plan: {args.out}; model commit: {resolved}")


def read_plan(path):
    receipt = json.loads(path.with_suffix(".sha256.json").read_text(encoding="utf-8"))
    if file_hash(path) != receipt["plan_sha256"]:
        raise ValueError("frozen plan hash mismatch; create a new version instead of editing")
    spec = json.loads(path.read_text(encoding="utf-8"))
    validate_spec(spec)
    for field in ("data_sha256", "source_sha256"):
        for name, expected in spec[field].items():
            path_in_repo = ROOT / relative_path(name)
            actual = (
                source_digest(path_in_repo) if field == "source_sha256" else file_hash(path_in_repo)
            )
            if actual != expected:
                raise ValueError(f"frozen {field} mismatch: {name}")
    return spec


def verify_model(model_dir):
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    for name, expected in metadata["artifact_files"].items():
        if file_hash(model_dir / name) != expected:
            raise ValueError(f"model artifact hash mismatch: {name}")
    state = json.loads((model_dir / "training-state.json").read_text(encoding="utf-8"))
    if state["state"] != "completed":
        raise ValueError("training has not completed")
    return metadata


def model_directory(spec, seed):
    return ROOT / spec["model_dir"] / f"seed-{seed}"


def best_seed(spec):
    models = [(seed, verify_model(model_directory(spec, seed))) for seed in spec["seeds"]]
    return max(
        models,
        key=lambda pair: (
            pair[1]["validation_metrics"]["eval_macro_f1"],
            pair[1]["validation_metrics"]["eval_accuracy"],
            -pair[0],
        ),
    )[0]


def train(args, spec):
    seeds = [args.seed] if args.seed is not None else spec["seeds"]
    if any(seed not in spec["seeds"] for seed in seeds):
        raise ValueError("seed must be in the frozen plan")
    if args.resume and len(seeds) != 1:
        raise ValueError("resume requires --seed")
    for seed in seeds:
        target = model_directory(spec, seed)
        if (target / "metadata.json").exists():
            metadata = verify_model(target)
            if metadata["revision"] != spec["revision"]:
                raise ValueError("completed model revision differs from plan")
            frozen_request = json.loads(
                (target / "training-request.json").read_text(encoding="utf-8")
            )
            if any(frozen_request.get(k) != v for k, v in spec["training"].items()):
                raise ValueError("completed training settings differ from plan")
            if metadata["train_sha256"] != file_hash(ROOT / spec["data_dir"] / "train.jsonl"):
                raise ValueError("completed model training data differs from plan")
            if metadata["validation_sha256"] != file_hash(
                ROOT / spec["data_dir"] / "validation.jsonl"
            ):
                raise ValueError("completed model validation data differs from plan")
            if metadata["catalog_signature"] != catalog_signature(
                load_catalog(ROOT / spec["data_dir"] / "catalog.json")
            ):
                raise ValueError("completed model catalog differs from plan")
            print(f"Already completed and verified: seed {seed}")
            continue
        command = [
            sys.executable,
            "-m",
            "services.train_bert",
            "--seed",
            str(seed),
            "--out",
            str(target),
            "--base-model",
            spec["base_model"],
            "--revision",
            spec["revision"],
        ]
        for name, filename in (
            ("train", "train.jsonl"),
            ("validation", "validation.jsonl"),
            ("catalog", "catalog.json"),
        ):
            command += [f"--{name}", str(ROOT / spec["data_dir"] / filename)]
        for key, value in spec["training"].items():
            command += ["--" + key.replace("_", "-"), str(value)]
        if args.resume:
            command += ["--resume", str(args.resume)]
        log_dir = ROOT / spec["model_dir"] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log = log_dir / f"seed-{seed}-{stamp}.log"
        print(f"Training seed {seed}; log: {log}", flush=True)
        with log.open("w", encoding="utf-8") as stream:
            subprocess.run(command, check=True, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if all((model_directory(spec, seed) / "metadata.json").exists() for seed in spec["seeds"]):
        selected = best_seed(spec)
        write_json(
            ROOT / spec["model_dir"] / "selection.json",
            {
                "seed": selected,
                "criterion": "validation macro_f1, accuracy, smaller seed",
                "model_version": verify_model(model_directory(spec, selected))["model_version"],
            },
        )


def serve(args, spec):
    seed = best_seed(spec) if args.seed is None else args.seed
    if seed not in spec["seeds"]:
        raise ValueError("seed must be in the frozen plan")
    model_dir = model_directory(spec, seed)
    verify_model(model_dir)
    env = dict(
        os.environ,
        MODEL_PATH=str(model_dir),
        DEVICE=args.device,
        TORCH_NUM_THREADS=str(args.threads),
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "services.bert_server:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--workers",
            "1",
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )


def service_metadata(base_url):
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        metadata = client.get("/metadata")
        metadata.raise_for_status()
        return health.json(), metadata.json()


def evaluate(args, spec):
    health, metadata = service_metadata(args.base_url)
    catalog = load_catalog(ROOT / spec["data_dir"] / "catalog.json")
    if not health.get("ready") or health.get("kind") != "bert" or health.get("synthetic"):
        raise ValueError("a ready, non-synthetic BERT service is required")
    if metadata["catalog_signature"] != catalog_signature(catalog):
        raise ValueError("service catalog differs from plan")
    if metadata["revision"] != spec["revision"] or metadata["seed"] not in spec["seeds"]:
        raise ValueError("service model revision or training seed differs from plan")
    if metadata["train_sha256"] != file_hash(ROOT / spec["data_dir"] / "train.jsonl"):
        raise ValueError("service training input differs from plan")
    settings = spec["measurement"]
    rates = (
        [None]
        if args.stage == "quality"
        else (args.rps if args.rps else settings["pilot_rps"] if args.stage == "pilot" else [])
    )
    if not rates:
        raise ValueError("formal measurement needs explicit --rps selected from pilot results")
    for rate in rates:
        if rate is not None and (not math.isfinite(rate) or rate <= 0):
            raise ValueError("RPS must be finite and positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / spec["output_dir"] / f"{spec['name']}-{args.stage}-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    index = {
        "state": "running",
        "stage": args.stage,
        "plan_sha256": file_hash(args.plan),
        "service_health": health,
        "model_metadata": metadata,
        "runs": [],
    }
    write_json(output / "index.json", index)
    try:
        for rate in rates:
            for repeat in range(settings["repeats"]):
                current_health, current_metadata = service_metadata(args.base_url)
                if current_health != health or current_metadata != metadata:
                    raise ValueError("service changed during the evaluation suite")
                config = {
                    "name": f"{spec['name']}-{args.stage}-{health['device']}-s{metadata['seed']}"
                    f"-r{rate}-rep{repeat + 1}",
                    "mode": "quality" if rate is None else "load",
                    "dataset": spec["data_dir"] + "/test.jsonl",
                    "catalog": spec["data_dir"] + "/catalog.json",
                    "output_dir": spec["output_dir"],
                    "adapter": {"kind": "bert", "base_url": args.base_url},
                    "seed": 42 + repeat,
                    **{
                        k: settings[k]
                        for k in (
                            "warmup",
                            "timeout_s",
                            "slo_ms",
                            "min_success_rate",
                            "max_scheduler_lag_ms",
                            "max_concurrency",
                        )
                    },
                    "environment": {
                        "service": health,
                        "model_version": metadata["model_version"],
                        "training_seed": metadata["seed"],
                        "repeat": repeat + 1,
                        "required_repeats": settings["repeats"],
                        "experiment_stage": args.stage,
                        "model_metadata": metadata,
                        "network_note": args.network_note,
                        "plan_sha256": file_hash(args.plan),
                    },
                }
                if rate is not None:
                    config.update(offered_rps=rate, duration_s=settings[f"{args.stage}_duration_s"])
                RunConfig(**config)
                config_path = output / f"r{rate}-repeat{repeat + 1}.json"
                write_json(config_path, config)
                run_dir = asyncio.run(run(config_path, ROOT))
                index["runs"].append(run_dir.relative_to(ROOT).as_posix())
                write_json(output / "index.json", index)
                time.sleep(settings["cooldown_s"])
        index["state"] = "completed"
    except BaseException as exc:
        index.update(
            state="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
            error_type=type(exc).__name__,
        )
        raise
    finally:
        write_json(output / "index.json", index)
    print(f"Evaluation index: {output / 'index.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--config", type=Path, default=Path("configs/bert-experiment.yaml"))
    command.add_argument("--source", type=Path)
    command.add_argument("--out", type=Path, default=Path("experiments/bert-native-v1/plan.json"))
    for name in ("train", "serve", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--plan", type=Path, required=True)
        if name in {"train", "serve"}:
            command.add_argument("--seed", type=int)
        if name == "train":
            command.add_argument("--resume", type=Path)
        elif name == "serve":
            command.add_argument("--device", choices=("cpu", "cuda"), required=True)
            command.add_argument("--threads", type=int, default=4)
            command.add_argument("--host", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8001)
        else:
            command.add_argument("--base-url", default="http://127.0.0.1:8001")
            command.add_argument("--stage", choices=("quality", "pilot", "formal"), required=True)
            command.add_argument("--rps", type=float, nargs="+")
            command.add_argument("--network-note", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        spec = read_plan(args.plan)
        {"train": train, "serve": serve, "evaluate": evaluate}[args.command](args, spec)


if __name__ == "__main__":
    main()
