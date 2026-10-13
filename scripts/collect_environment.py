"""Collect a read-only environment snapshot without dumping secrets or .env files."""

import argparse
import importlib.metadata
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from decisionbench.artifacts import write_json


def command_output(args):
    if not shutil.which(args[0]):
        return {"available": False}
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        return {
            "available": True,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "error_type": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output exists; use a new timestamped snapshot")
    snapshot = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "packages": sorted(
            f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
        ),
        "gpu": command_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version,power.limit",
                "--format=csv,noheader",
            ]
        ),
        "cpu": command_output(["lscpu"]),
        "docker": command_output(["docker", "version", "--format", "{{.Server.Version}}"]),
        "note": "Read-only snapshot; does not attest to remote API hardware or model versions.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, snapshot)
    print(args.out)


if __name__ == "__main__":
    main()
