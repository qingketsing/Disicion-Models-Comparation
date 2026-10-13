import argparse
import csv
import json
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Compare completed runs; do not mix synthetic with real"
)
parser.add_argument("--results", type=Path, default=Path("results"))
parser.add_argument("--out", type=Path, default=Path("results/comparison.csv"))
args = parser.parse_args()
rows = []
for path in sorted(args.results.glob("*/summary.json")):
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    if manifest["state"] != "completed":
        continue
    s = json.loads(path.read_text(encoding="utf-8"))
    cost_path = path.parent / "cost.json"
    cost = json.loads(cost_path.read_text(encoding="utf-8")) if cost_path.exists() else s["cost"]
    rows.append(
        {
            "run": path.parent.name,
            "adapter": manifest["config"]["adapter"]["kind"],
            "mode": s["mode"],
            "synthetic": s["synthetic"],
            "dataset_sha256": manifest["dataset_sha256"],
            "catalog_sha256": ";".join(manifest["catalog_sha256"]),
            "accuracy": s["quality"]["accuracy"],
            "macro_f1": s["quality"]["macro_f1"],
            "success_rate": s["success_rate"],
            "goodput_qps": s["goodput_qps"],
            "p95_ms": s["latency_attempted"]["p95_ms"],
            "slo_capacity_candidate": s["slo_capacity_candidate"],
            "currency": cost.get("currency"),
            "cost_per_million_slo_valid": cost.get("cost_per_million_slo_valid"),
            "cost_source": "cost.json" if cost_path.exists() else "summary.json",
        }
    )
if not rows:
    parser.error("no completed runs found")
args.out.parent.mkdir(parents=True, exist_ok=True)
with args.out.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(f"Exported {len(rows)} runs to {args.out}")
