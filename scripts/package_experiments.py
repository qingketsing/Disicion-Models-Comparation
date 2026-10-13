"""Build an upload ZIP from explicit source paths, optionally with a frozen bundle."""

import argparse
import zipfile
from pathlib import Path


def package(root, output, bundle=None):
    paths = []
    for folder in (
        "decisionbench",
        "services",
        "scripts",
        "tests",
        "configs",
        "docs",
        "infra",
        "refine-logs",
        "data/fixtures",
    ):
        paths.extend(
            p
            for p in (root / folder).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    for name in (
        "README.md",
        "pyproject.toml",
        "requirements-controller.lock.txt",
        "requirements-experiments.lock.txt",
        "docker-compose.yaml",
        ".env.example",
        ".gitignore",
        ".dockerignore",
        "MANIFEST.md",
    ):
        if (root / name).exists():
            paths.append(root / name)
    if bundle is not None:
        bundle.resolve().relative_to((root / "experiments").resolve())
        if not (bundle / "plan.json").exists():
            raise ValueError("bundle must be a prepared directory under experiments/")
        paths.extend(p for p in bundle.rglob("*") if p.is_file())
    if output.exists():
        raise ValueError("archive exists; choose a new version filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            archive.write(path, path.relative_to(root).as_posix())
    return len(set(paths))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    try:
        count = package(
            args.root.resolve(), args.out.resolve(), args.bundle.resolve() if args.bundle else None
        )
        print(f"Packaged {count} files: {args.out}")
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
