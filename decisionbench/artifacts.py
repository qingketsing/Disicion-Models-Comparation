import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


def file_hash(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def create_run(root, config, config_path, dataset_path, catalog_paths):
    import uuid

    now = datetime.now(timezone.utc)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in config.name)
    output = root / config.output_dir / f"{now:%Y%m%dT%H%M%SZ}-{safe_name}-{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    shutil.copyfile(dataset_path, inputs / "dataset.jsonl")
    shutil.copyfile(config_path, inputs / "config.yaml")
    for i, path in enumerate(catalog_paths):
        shutil.copyfile(path, inputs / f"catalog-{i}.json")
    source_root = Path(__file__).resolve().parents[1]
    source_paths = sorted(
        p
        for folder in ("decisionbench", "services", "scripts")
        for p in (source_root / folder).rglob("*.py")
    )
    source_paths.extend(
        source_root / name
        for name in ("pyproject.toml", "docker-compose.yaml", "requirements-controller.lock.txt")
        if (source_root / name).exists()
    )
    code_hashes = {str(p.relative_to(source_root)): file_hash(p) for p in source_paths}
    snapshot = output / "source"
    for p in source_paths:
        target = snapshot / p.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
        git_dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=source_root, text=True
            ).strip()
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        git_commit, git_dirty = None, None
    manifest = {
        "schema_version": "0.1",
        "created_at_utc": now.isoformat(),
        "state": "running",
        "config": asdict(config),
        "config_sha256": file_hash(config_path),
        "dataset_sha256": file_hash(dataset_path),
        "catalog_sha256": [file_hash(p) for p in catalog_paths],
        "code_sha256": hashlib.sha256(json.dumps(code_hashes, sort_keys=True).encode()).hexdigest(),
        "source_files": code_hashes,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": sorted(
            f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
        ),
        "worker_environment": config.environment,
        "mock_adapter": config.adapter["kind"] == "mock",
        "fixture_dataset": (root / "data/fixtures").resolve() in dataset_path.resolve().parents,
        "synthetic": config.adapter["kind"] == "mock"
        or (root / "data/fixtures").resolve() in dataset_path.resolve().parents
        or bool(config.environment.get("service", {}).get("synthetic", False)),
        "notes": "Worker hardware/model revision must be supplied; Controller metadata is automatic.",
    }
    write_json(output / "manifest.json", manifest)
    return output, manifest
