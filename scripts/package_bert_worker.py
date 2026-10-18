"""Package the current BERT implementation for a worker without credentials or weights."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.out.exists():
        parser.error("output already exists; choose a new archive name")
    names = [
        "README.md",
        "pyproject.toml",
        "requirements-controller.lock.txt",
        "requirements-bert.txt",
        "requirements-bert.lock.txt",
        "docker-compose.yaml",
        ".gitignore",
        ".dockerignore",
        ".gitattributes",
        ".env.example",
    ]
    for folder, suffix in (
        ("decisionbench", ".py"),
        ("services", ".py"),
        ("scripts", ".py"),
        ("tests", ".py"),
        ("configs", ".yaml"),
        ("configs", ".json"),
        ("docs", ".md"),
        ("docs", ".json"),
    ):
        names += [p.relative_to(root).as_posix() for p in (root / folder).glob("*" + suffix)]
    names += [p.relative_to(root).as_posix() for p in (root / "infra").iterdir() if p.is_file()]
    names += [
        p.relative_to(root).as_posix() for p in (root / "data/fixtures").iterdir() if p.is_file()
    ]
    for directory in (
        "reports/experiment-results-20261015/data-provenance",
        "reports/qwen-jev-main-paired-20261015",
    ):
        names += [
            p.relative_to(root).as_posix() for p in (root / directory).iterdir() if p.is_file()
        ]
    contents = {name: (root / name).read_bytes() for name in sorted(set(names))}
    manifest = {
        "scope": "source, configs, fixture data, descriptions and historical paired results",
        "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    }
    try:
        manifest["base_git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        manifest["git_dirty"] = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        manifest["base_git_commit"] = None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
        archive.writestr("worker-package-manifest.json", json.dumps(manifest, indent=2) + "\n")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.out.with_suffix(args.out.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"{args.out}: {len(contents)} files; SHA256 {digest}")


if __name__ == "__main__":
    main()
