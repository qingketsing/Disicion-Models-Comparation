"""Preview or start a local, pinned vLLM worker on Linux without Docker."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json


def worker_command(config):
    python = Path(config["worker_python"])
    model = Path(config["model_path"])
    if not python.is_file() or not (model / "config.json").is_file():
        raise ValueError("worker interpreter or downloaded model is missing")
    if config["model_revision"] in {"main", "latest", "TODO"}:
        raise ValueError("pin an immutable model revision")
    manifest_path = model / "download-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("verified") or manifest["snapshot_id"] != config["model_revision"]:
        raise ValueError("downloaded model manifest does not match the pinned snapshot")
    for entry in manifest["files"]:
        path = model / entry["Path"]
        if path.stat().st_size != entry["Size"] or file_hash(path) != entry["Sha256"]:
            raise ValueError(f"downloaded model changed: {entry['Path']}")
    if config["dtype"] not in {"bfloat16", "float16"}:
        raise ValueError("dtype must be bfloat16 or float16")
    return [
        str(python),
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        str(model),
        "--served-model-name",
        config["served_model_name"],
        "--host",
        "127.0.0.1",
        "--port",
        str(config.get("port", 8000)),
        "--dtype",
        config["dtype"],
        "--max-model-len",
        str(config["max_model_len"]),
        "--gpu-memory-utilization",
        str(config["gpu_memory_utilization"]),
        "--max-num-seqs",
        str(config.get("max_num_seqs", 32)),
        "--no-enable-prefix-caching",
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New launch record JSON")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--start", action="store_true", help="Default only previews")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    command = worker_command(config)
    if args.out.exists() or (args.start and args.log.exists()):
        parser.error("use new record and log filenames to retain previous attempts")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "argv": command,
        "config_sha256": file_hash(args.config),
        "model_revision": config["model_revision"],
        "started": args.start,
    }
    if args.start:
        if os.name != "posix":
            parser.error("native worker launcher requires Linux")
        args.log.parent.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        with args.log.open("x", encoding="utf-8") as stream:
            process = subprocess.Popen(
                command,
                stdout=stream,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
        record["pid"] = process.pid
    write_json(args.out, record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
