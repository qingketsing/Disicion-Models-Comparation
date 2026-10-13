"""Run the complete experiment workflow locally with fixture data and mock adapters only."""

import argparse
import asyncio
import shutil
from pathlib import Path

import yaml

from decisionbench.analysis import analyze
from decisionbench.artifacts import file_hash, write_json
from decisionbench.suite import prepare, run_plan


async def smoke(root, name):
    source = root / "experiments" / name / "dataset"
    source.mkdir(parents=True, exist_ok=False)
    for filename in ("test.jsonl", "catalog.json"):
        shutil.copyfile(root / "data/fixtures" / filename, source / filename)
    write_json(
        source / "provenance.json",
        {
            "descriptions_reviewed": True,
            "synthetic_fixture": True,
            "note": "Curated toy fixture for software verification; no real benchmark data.",
            "normalized_sha256": {
                name: file_hash(source / name) for name in ("test.jsonl", "catalog.json")
            },
        },
    )
    config = source.parent / "suite.yaml"
    spec = {
        "name": name,
        "dataset_dir": source.relative_to(root).as_posix(),
        "cooldown_s": 0,
        "models": {
            model: {"adapter": {"kind": "mock", "delay_ms": 1}, "warmup": 2}
            for model in ("qwen", "jev")
        },
        "common": {"max_scheduler_lag_ms": 100, "max_concurrency": 2},
        "blocks": {
            "main": {"enabled": True, "dataset": "test.jsonl", "repeats": 1},
            "load": {
                "enabled": True,
                "dataset": "test.jsonl",
                "repeats": 1,
                "rates": [10, 20],
                "duration_s": 0.2,
            },
            "scale": {
                "enabled": True,
                "dataset": "test.jsonl",
                "sizes": [2, 3],
                "seeds": [42, 43],
                "samples_per_anchor_class": 1,
            },
        },
    }
    config.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    plan = prepare(config, root, source.parent / "bundle")
    await run_plan(plan, root, ["main"], [], execute=True)
    await run_plan(plan, root, ["load", "scale"], [], execute=True)
    analyze(plan, root, root / "reports" / name, plots=True)
    print(f"Mock-only workflow complete: reports/{name}/REPORT.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--name", default="local-smoke-v1")
    args = parser.parse_args()
    if not args.name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in args.name):
        parser.error("name must be a lowercase ASCII identifier")
    asyncio.run(smoke(args.root.resolve(), args.name))


if __name__ == "__main__":
    main()
