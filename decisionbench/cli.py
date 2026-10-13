import argparse
import asyncio
import json
from pathlib import Path

from decisionbench.adapters import create_adapter
from decisionbench.artifacts import create_run, write_json
from decisionbench.config import load_config, resolve_path
from decisionbench.datasets import load_catalog, load_samples, read_jsonl
from decisionbench.metrics import request_cost, summarize
from decisionbench.runners import load, quality, warmup


async def run(config_path: Path, root: Path, on_created=None):
    config = load_config(config_path)
    catalog_paths = [resolve_path(root, config.catalog)]
    if config.mode == "dynamic":
        catalog_paths = [resolve_path(root, s["catalog"]) for s in config.stages]
    catalogs = [load_catalog(path) for path in catalog_paths]
    samples = load_samples(resolve_path(root, config.dataset), catalogs)
    # Validate prices before any real requests are sent.
    request_cost([], 0, config.cost, config.slo_ms)
    adapter = create_adapter(config.adapter, config.max_concurrency)
    output = None
    manifest = None
    try:
        output, manifest = create_run(
            root, config, config_path, resolve_path(root, config.dataset), catalog_paths
        )
        if on_created is not None:
            on_created(output)
        print(f"Run directory: {output}", flush=True)
        with (output / "warmup_requests.jsonl").open("w", encoding="utf-8") as stream:
            await warmup(
                adapter,
                samples,
                catalogs[0],
                config,
                lambda row: stream.write(json.dumps(row, allow_nan=False) + "\n"),
            )
        with (output / "requests.jsonl").open("w", encoding="utf-8") as stream:

            def emit(row):
                # Sanitize invalid numeric responses before JSON serialization.
                if row["status"] == "invalid_output":
                    for key in ("scores", "confidence", "input_tokens", "output_tokens"):
                        try:
                            json.dumps(row[key], allow_nan=False)
                        except (ValueError, TypeError):
                            row[key] = {} if key == "scores" else None
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()

            if config.mode == "quality":
                elapsed = await quality(adapter, samples, catalogs[0], config, emit)
            else:
                stages = [(s["at_s"], c) for s, c in zip(config.stages, catalogs)]
                if config.mode == "load":
                    stages = [(0, catalogs[0])]
                elapsed = await load(adapter, samples, stages, config, emit)
        records = read_jsonl(output / "requests.jsonl")
        labels = set().union(*(c.labels for c in catalogs))
        summary = summarize(records, config, elapsed, labels)
        summary["synthetic"] = manifest["synthetic"]
        summary["warmup_requests"] = config.warmup
        if config.mode == "dynamic":
            summary["dynamic_note"] = (
                "Catalog replay only; retraining and recovery-time measurement are P1."
            )
            summary["stages"] = []
            for i, catalog in enumerate(catalogs):
                rows = [r for r in records if r["phase"] == f"stage_{i}"]
                stage_end = (
                    config.stages[i + 1]["at_s"] if i + 1 < len(catalogs) else config.duration_s
                )
                start = config.stages[i]["at_s"]
                stage_elapsed = (
                    max(stage_end, max((r["completed_s"] for r in rows), default=0)) - start
                )
                item = summarize(rows, config, stage_elapsed, labels)
                item.update(stage=i, at_s=start, catalog_version=catalog.version)
                item["arrival_window_s"] = stage_end - start
                item["observed_offered_rps"] = len(rows) / (stage_end - start)
                item["cost"] = {
                    "configured": False,
                    "note": "Overlapping stage drain costs are accounted once at run level",
                }
                summary["stages"].append(item)
        write_json(output / "summary.json", summary)
        manifest.update(state="completed", elapsed_s=elapsed)
        write_json(output / "manifest.json", manifest)
        print(
            json.dumps(
                {
                    "mode": config.mode,
                    "requests": len(records),
                    "success_rate": summary["success_rate"],
                    "accuracy": summary["quality"]["accuracy"],
                    "goodput_qps": summary["goodput_qps"],
                    "synthetic": summary["synthetic"],
                },
                indent=2,
            )
        )
        return output
    except BaseException as exc:
        if output is not None and manifest is not None:
            manifest.update(
                state="interrupted"
                if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError))
                else "failed",
                error_type=type(exc).__name__,
            )
            write_json(output / "manifest.json", manifest)
        raise
    finally:
        await adapter.close()


def main():
    parser = argparse.ArgumentParser(description="DecisionBench reproducible model harness")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("run")
    command.add_argument("-c", "--config", type=Path, required=True)
    command.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Root for paths inside config"
    )
    command = sub.add_parser("cost", help="Recompute cost offline; sends no model requests")
    command.add_argument("run_dir", type=Path)
    command.add_argument(
        "--pricing", type=Path, required=True, help="JSON price mapping with currency"
    )
    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(run(args.config.resolve(), args.root.resolve()))
    elif args.command == "cost":
        manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest["state"] != "completed":
            parser.error("cost requires a completed run")
        pricing = json.loads(args.pricing.read_text(encoding="utf-8"))
        result = request_cost(
            read_jsonl(args.run_dir / "requests.jsonl"),
            manifest["elapsed_s"],
            pricing,
            manifest["config"]["slo_ms"],
        )
        write_json(args.run_dir / "cost.json", result)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
