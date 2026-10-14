"""Launch the verified native Worker with a pinned structured-output backend."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json
from scripts.launch_qwen_native import worker_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    options = config["structured_outputs"]
    if options != {"backend": "guidance", "disable_fallback": True}:
        raise ValueError("use the verified guidance backend with fallback disabled")
    if os.name != "posix" or args.out.exists() or args.log.exists():
        raise ValueError("Linux and new launch/log paths are required")
    command = worker_command(config) + ["--structured-outputs-config", json.dumps(options)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("x", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            start_new_session=True,
        )
    record = {
        "pid": process.pid,
        "argv": command,
        "config_sha256": file_hash(args.config),
        "model_revision": config["model_revision"],
        "structured_outputs": options,
    }
    write_json(args.out, record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
