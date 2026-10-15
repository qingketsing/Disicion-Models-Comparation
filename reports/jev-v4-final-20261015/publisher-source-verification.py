"""Reconstruct native MASSIVE rows without modifying frozen or normalized data."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.prepare_datasets import massive, stratified_subset


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


root = Path("data/normalized/massive-ai-v1")
provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
source, expected = next(iter(provenance["source_sha256"].items()))
assert digest(source) == expected
splits, _ = massive(Path(source), "en-US")
splits["checkpoint-300"] = stratified_subset(splits["validation"], 300, 42)
sizes = {}
for split, rows in splits.items():
    actual = [json.loads(line) for line in (root / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert sorted(rows, key=lambda row: row["sample_id"]) == actual, split
    sizes[split] = len(actual)
for name, expected_normalized in provenance["normalized_sha256"].items():
    assert digest(root / name) == expected_normalized, name
out = {
    "status": "PASS",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "review_independence": "deterministic",
    "acceptance_status": "accepted",
    "publisher_url": provenance["source_urls"][0],
    "publisher_archive": source,
    "publisher_sha256": expected,
    "publisher_bytes": Path(source).stat().st_size,
    "native_partition_text_intent_and_ids_exact": True,
    "split_sizes": sizes,
    "normalized_sha256": provenance["normalized_sha256"],
    "normalization_script_sha256": digest("scripts/prepare_datasets.py"),
    "scope": "Exact publisher archive hash plus semantic row equality; no GT, catalog or frozen run bytes modified.",
}
Path("reports/jev-v4-final-20261015/publisher-source-verification.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(json.dumps(out, indent=2))
