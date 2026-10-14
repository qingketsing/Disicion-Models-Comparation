"""Check a dataset with the local pinned Qwen tokenizer; never sends model requests.

Useful during preparation before human descriptions are reviewed. A draft result
must be repeated after the reviewed catalog and final suite have been frozen.
"""

import argparse
import json
from pathlib import Path

from decisionbench.adapters import qwen_messages
from decisionbench.artifacts import file_hash, write_json
from decisionbench.datasets import load_catalog, load_samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.max_model_len < 1 or args.max_tokens < 1:
        parser.error("choose a new output and positive token limits")
    manifest_path = args.model_dir / "download-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("verified"):
        parser.error("downloaded model must be hash verified first")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True)
    catalog_path = args.dataset_dir / "catalog.json"
    catalog = load_catalog(catalog_path)
    checks = []
    for name in ("validation.jsonl", "test.jsonl", "checkpoint-300.jsonl"):
        path = args.dataset_dir / name
        samples = load_samples(path, [catalog])
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
        required = lengths[longest] + args.max_tokens
        checks.append(
            {
                "dataset": name,
                "dataset_sha256": file_hash(path),
                "samples": len(samples),
                "max_input_tokens": lengths[longest],
                "longest_sample_id": samples[longest].sample_id,
                "required_context_including_output": required,
                "fits": required <= args.max_model_len,
            }
        )
    provenance = json.loads((args.dataset_dir / "provenance.json").read_text(encoding="utf-8"))
    write_json(
        args.out,
        {
            "model_revision": manifest["snapshot_id"],
            "manifest_sha256": file_hash(manifest_path),
            "catalog_sha256": file_hash(catalog_path),
            "max_model_len": args.max_model_len,
            "descriptions_reviewed": provenance["descriptions_reviewed"],
            "checks": checks,
            "note": "Preparation only. Repeat on final reviewed catalogs, including scale variants.",
        },
    )
    print(json.dumps(checks, indent=2))
    if not all(check["fits"] for check in checks):
        parser.error("inputs exceed configured context; do not truncate the catalog")


if __name__ == "__main__":
    main()
