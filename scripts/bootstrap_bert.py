"""Create an isolated Python 3.12 BERT environment on Linux or Windows."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python 3.12 interpreter")
    parser.add_argument("--venv", type=Path, default=Path(".venv-bert"))
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--cuda-wheel", choices=("cu126", "cu128", "cu130"), default="cu128")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = subprocess.check_output(
        [args.python, "-c", "import sys; print('%s.%s' % sys.version_info[:2])"],
        text=True,
    ).strip()
    if version != "3.12":
        parser.error("use a Python 3.12 interpreter (for example: uv python install 3.12)")
    destination = args.venv.resolve()
    if not destination.exists():
        subprocess.run([args.python, "-m", "venv", str(destination)], check=True)
    executable = destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        parser.error("destination exists but is not a virtual environment")
    actual_version = subprocess.check_output(
        [str(executable), "-c", "import sys; print('%s.%s' % sys.version_info[:2])"],
        text=True,
    ).strip()
    if actual_version != "3.12":
        parser.error("existing virtual environment must use Python 3.12")
    index = "https://download.pytorch.org/whl/" + (
        "cpu" if args.device == "cpu" else args.cuda_wheel
    )
    commands = [
        ["-m", "pip", "install", "--upgrade", "pip"],
        [
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "torch==2.9.1",
            "--index-url",
            index,
        ],
        [
            "-m",
            "pip",
            "install",
            "-r",
            str(root / "requirements-bert.txt"),
            "-c",
            str(root / "requirements-bert.lock.txt"),
        ],
        ["-m", "pip", "install", "--no-deps", "-e", str(root)],
        ["-m", "pip", "check"],
    ]
    for command in commands:
        subprocess.run([str(executable), *command], check=True, cwd=root)
    receipt = (
        root / "results" / ("bert-setup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    )
    receipt.mkdir(parents=True, exist_ok=False)
    freeze = subprocess.check_output([str(executable), "-m", "pip", "freeze", "--all"], text=True)
    (receipt / "pip-freeze.txt").write_text(freeze, encoding="utf-8")
    (receipt / "setup.json").write_text(
        json.dumps(
            {
                "device": args.device,
                "torch_index": index,
                "python": str(executable),
                "python_version": version,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            str(executable),
            "-m",
            "scripts.check_bert_environment",
            "--device",
            args.device,
            "--out",
            str(receipt / "environment.json"),
        ],
        check=True,
        cwd=root,
    )
    print(f"Environment ready: {executable}\nReceipt: {receipt}")


if __name__ == "__main__":
    main()
