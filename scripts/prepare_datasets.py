"""Normalize original publisher files without executing Hugging Face dataset scripts."""

import argparse
import csv
import hashlib
import json
import random
import tarfile
import urllib.request
from collections import defaultdict
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json

BANKING_REVISION = "57ec275d8078af65b7731c2a98be812d844a6d6b"
MASSIVE_URL = (
    "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz"
)


def download(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    urllib.request.urlretrieve(url, temporary)
    temporary.replace(target)


def stratified_subset(rows, count, seed):
    if count <= 0 or count > len(rows):
        raise ValueError("checkpoint size must be positive and no greater than validation size")
    buckets = defaultdict(list)
    for row in rows:
        buckets[row["label"]].append(row)
    rng = random.Random(seed)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    result = []
    while len(result) < count:
        for label in sorted(buckets):
            if buckets[label] and len(result) < count:
                result.append(buckets[label].pop())
    rng.shuffle(result)
    return result


def massive(source, locale):
    if source.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(source, "r:gz") as archive:
            members = [
                m
                for m in archive.getmembers()
                if m.isfile() and m.name.endswith(f"/data/{locale}.jsonl")
            ]
            if len(members) != 1:
                raise ValueError("archive must contain exactly one matching locale")
            # Read the selected file only; never extract archive paths to the filesystem.
            with archive.extractfile(members[0]) as stream:
                raw = [json.loads(line) for line in stream if line.strip()]
    else:
        with source.open(encoding="utf-8") as stream:
            raw = [json.loads(line) for line in stream if line.strip()]
    splits = defaultdict(list)
    for row in raw:
        if row["locale"] != locale:
            raise ValueError("locale mismatch in source file")
        split = {"train": "train", "dev": "validation", "test": "test"}[row["partition"]]
        splits[split].append(
            {
                "sample_id": f"massive-{locale}-{split}-{row['id']}",
                "text": row["utt"],
                "label": row["intent"],
            }
        )
    return splits, {str(source): file_hash(source)}


def banking(source, seed):
    splits = defaultdict(list)
    for split in ("train", "test"):
        with (source / f"{split}.csv").open(encoding="utf-8", newline="") as stream:
            for i, row in enumerate(csv.DictReader(stream)):
                splits[split].append(
                    {
                        "sample_id": f"banking77-{split}-{i:06d}",
                        "text": row["text"],
                        "label": row["category"],
                    }
                )
    buckets = defaultdict(list)
    for row in splits["train"]:
        buckets[row["label"]].append(row)
    rng = random.Random(seed)
    splits["train"] = []
    for label in sorted(buckets):
        rows = buckets[label]
        rng.shuffle(rows)
        n = max(1, int(len(rows) * 0.1))
        splits["validation"].extend(rows[:n])
        splits["train"].extend(rows[n:])
    return splits, {
        str(source / f"{s}.csv"): file_hash(source / f"{s}.csv") for s in ("train", "test")
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", choices=["massive", "banking77"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, help="MASSIVE JSONL/tarball or BANKING77 CSV directory"
    )
    parser.add_argument("--download", action="store_true", help="Download original publisher files")
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--checkpoint-size", type=int, default=300)
    parser.add_argument(
        "--descriptions", type=Path, help="Reviewed JSON label-to-description mapping"
    )
    parser.add_argument("--description-reviewer", choices=["human", "ai"], default="human")
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("output must be empty; choose a new frozen dataset directory")
    if bool(args.source) == args.download:
        parser.error("choose exactly one of --source or --download")
    source = args.source
    urls = []
    if args.download:
        if args.name == "massive":
            source = Path("data/raw/amazon-massive-dataset-1.1.tar.gz")
            urls = [MASSIVE_URL]
            if not source.exists():
                download(MASSIVE_URL, source)
        else:
            source = Path("data/raw/banking77") / BANKING_REVISION
            for split in ("train", "test"):
                url = f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{BANKING_REVISION}/banking_data/{split}.csv"
                urls.append(url)
                if not (source / f"{split}.csv").exists():
                    download(url, source / f"{split}.csv")
    splits, hashes = (
        massive(source, args.locale) if args.name == "massive" else banking(source, args.seed)
    )
    if not all(splits.get(s) for s in ("train", "validation", "test")):
        raise ValueError("source must provide nonempty train, validation and test splits")
    labels = sorted({r["label"] for rows in splits.values() for r in rows})
    descriptions = (
        json.loads(args.descriptions.read_text(encoding="utf-8"))
        if args.descriptions
        else {label: label.replace("_", " ") for label in labels}
    )
    if set(descriptions) != set(labels) or not all(
        isinstance(v, str) and v for v in descriptions.values()
    ):
        raise ValueError("descriptions must cover exactly the source labels")
    splits[
        "checkpoint-300" if args.checkpoint_size == 300 else f"checkpoint-{args.checkpoint_size}"
    ] = stratified_subset(splits["validation"], args.checkpoint_size, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for split, rows in splits.items():
        with (args.out / f"{split}.jsonl").open("w", encoding="utf-8") as stream:
            for row in sorted(rows, key=lambda r: r["sample_id"]):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    signature = hashlib.sha256(json.dumps(descriptions, sort_keys=True).encode()).hexdigest()[:12]
    write_json(
        args.out / "catalog.json", {"version": f"{args.name}-{signature}", "labels": descriptions}
    )
    write_json(
        args.out / "provenance.json",
        {
            "dataset": args.name,
            "locale": args.locale if args.name == "massive" else "en",
            "seed": args.seed,
            "source_urls": urls,
            "source_sha256": hashes,
            "banking_revision": BANKING_REVISION
            if args.name == "banking77" and args.download
            else None,
            "sizes": {k: len(v) for k, v in splits.items()},
            "split_policy": "MASSIVE native partitions; BANKING77 10% per-class train holdout, original test unchanged",
            "descriptions_reviewed": args.descriptions is not None,
            "description_reviewer": args.description_reviewer if args.descriptions else None,
            "description_mapping_sha256": file_hash(args.descriptions)
            if args.descriptions
            else None,
            "description_note": (
                "AI-authored and AI-reviewed from training examples; not human-reviewed."
                if args.descriptions and args.description_reviewer == "ai"
                else "Reviewed mapping supplied."
                if args.descriptions
                else "Generated label names are placeholders; review before checkpoint acceptance"
            ),
            "license": "CC BY 4.0; retain publisher attribution in reports",
            "normalized_sha256": {p.name: file_hash(p) for p in sorted(args.out.glob("*.json*"))},
        },
    )
    print(
        f"Prepared {args.name}: {args.out}; descriptions_reviewed={args.descriptions is not None}"
    )


if __name__ == "__main__":
    main()
