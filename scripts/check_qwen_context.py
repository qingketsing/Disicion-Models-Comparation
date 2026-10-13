"""Measure exact Qwen chat input lengths using a frozen tokenizer, without inference."""

import argparse
from pathlib import Path

from decisionbench.adapters import qwen_messages
from decisionbench.analysis import read_json
from decisionbench.artifacts import write_json
from decisionbench.config import load_config
from decisionbench.datasets import load_catalog, load_samples
from decisionbench.metrics import percentile
from decisionbench.suite import verify_bundle


def check_plan(plan_path, root, tokenizer, max_model_len):
    plan = read_json(plan_path)
    verify_bundle(plan, root)
    seen, checks = set(), []
    for job in plan["jobs"]:
        config = load_config(root / job["config"])
        if config.adapter["kind"] != "qwen":
            continue
        key = job["dataset_sha256"], job["catalog_sha256"], config.adapter.get("max_tokens", 64)
        if key in seen:
            continue
        seen.add(key)
        catalog = load_catalog(root / config.catalog)
        samples = load_samples(root / config.dataset, [catalog])
        lengths = [
            len(
                tokenizer.apply_chat_template(
                    qwen_messages(sample.model_input(), catalog),
                    tokenize=True,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
            )
            for sample in samples
        ]
        longest = max(range(len(samples)), key=lengths.__getitem__)
        required = lengths[longest] + config.adapter.get("max_tokens", 64)
        checks.append(
            {
                "job": job["id"],
                "samples": len(samples),
                "max_input_tokens": lengths[longest],
                "p95_input_tokens": percentile(lengths, 95),
                "longest_sample_id": samples[longest].sample_id,
                "required_context_including_output": required,
                "max_model_len": max_model_len,
                "fits": required <= max_model_len,
            }
        )
    if not checks:
        raise ValueError("no Qwen jobs found")
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--revision", required=True, help="Same immutable revision as vLLM")
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output exists; choose a new context-check filename")
    if args.revision in {"main", "latest"} or args.max_model_len < 1:
        parser.error("use a frozen model revision and a positive context length")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    checks = check_plan(args.plan.resolve(), args.root.resolve(), tokenizer, args.max_model_len)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, {"model": args.model, "revision": args.revision, "checks": checks})
    if not all(check["fits"] for check in checks):
        parser.error("inputs exceed context length; update deployment and suite before running")
    print(f"All {len(checks)} unique input/catalog combinations fit: {args.out}")


if __name__ == "__main__":
    main()
