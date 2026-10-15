"""Offline, explicit Jev evidence snapshots with member and archive SHA256 receipts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def snapshot(root: Path, paths: set[Path], target: Path) -> dict:
    root = root.resolve()
    target = target.resolve()
    receipt_path = target.with_suffix(".receipt.json")
    if target.exists() or receipt_path.exists():
        raise FileExistsError(target)
    files: dict[str, Path] = {}
    for item in sorted(paths):
        for source in sorted(item.rglob("*")) if item.is_dir() else [item]:
            if source.is_symlink():
                raise ValueError(f"Symlink excluded: {source}")
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            name = source.resolve().relative_to(root).as_posix()
            if source.name == ".env" or source.suffix in {".pyc", ".pyd"}:
                raise ValueError(f"Unexpected runtime/secret file: {name}")
            files[name] = source
    members = {name: sha256(source) for name, source in files.items()}
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        for name, source in files.items():
            archive.add(source, arcname=name, recursive=False)
    with tarfile.open(target, "r:gz") as archive:
        actual = {}
        for member in archive:
            if not member.isfile():
                raise ValueError(member.name)
            stream = archive.extractfile(member)
            assert stream is not None
            actual[member.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != members:
        raise ValueError("Archive member mismatch")
    for name, source in files.items():
        if sha256(source) != members[name]:
            raise ValueError(f"Source changed during capture: {name}")
    receipt = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive": target.relative_to(root).as_posix(),
        "archive_sha256": sha256(target),
        "members_count": len(members),
        "source_and_archive_members_verified": True,
        "members_sha256": members,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return {key: value for key, value in receipt.items() if key != "members_sha256"}


def evidence_paths(root: Path) -> set[Path]:
    ledger = root / "reports/jev-v4-final-20261015/historical-run-cost-ledger.csv"
    with ledger.open(encoding="utf-8-sig", newline="") as handle:
        paths = {root / row["run"] for row in csv.DictReader(handle)}
    for run in paths:
        if not (run / "manifest.json").is_file():
            raise FileNotFoundError(run)
    for plan in (root / "experiments").glob("*jev*/plan.json"):
        paths.add(plan.parent)
        suite = root / "results/suites" / sha256(plan)
        if suite.exists():
            paths.add(suite)
    paths.update((root / "results/execution-20261014").glob("*jev*"))
    paths.update((root / "configs").glob("*jev*.yaml"))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["evidence", "deliverables"])
    args = parser.parse_args()
    root = Path.cwd()
    if args.kind == "evidence":
        paths = evidence_paths(root)
    else:
        paths = set()
        for pattern in (
            "docs/*JEV*", "docs/EXECUTION_LOG_20261014.md",
            "refine-logs/EXPERIMENT_TRACKER.md", "EXPERIMENT_AUDIT.*",
            "reports/jev-v4-final-20261015", "reports/jev-error-review-20261015",
            "reports/qwen-jev-main-paired-20261015", "orchestration/*.py",
            "tests/*.py",
            "configs/*jev*.yaml", ".aris/traces/experiment-audit/2026-10-15_run01",
            ".aris/meta/events.jsonl", "dist/jev-v4-final-evidence-snapshot.tar.receipt.json",
            "dist/jev-v4-source-provenance-snapshot.tar.receipt.json",
            "dist/jev-v4-final-git.bundle", "dist/jev-v4-final-git-receipt.json",
            "results/execution-20261014/jev-v4-final-verification.json",
        ):
            paths.update(root.glob(pattern))
    print(json.dumps(snapshot(root, paths, root / f"dist/jev-v4-final-{args.kind}-snapshot.tar.gz"), indent=2))


if __name__ == "__main__":
    main()
