"""Offline tiny BERT: train -> real HTTP -> quality/load -> offline analysis."""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from decisionbench.artifacts import write_json
from decisionbench.cli import run
from decisionbench.datasets import read_jsonl
from scripts.analyze_bert import analyze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    from transformers import BertConfig, BertModel, BertTokenizerFast

    base = out / "tiny-base"
    base.mkdir()
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "set", "cancel", "my", "alarm"]
    (base / "vocab.txt").write_text("\n".join(vocab) + "\n", encoding="utf-8")
    tokenizer = BertTokenizerFast(vocab_file=str(base / "vocab.txt"))
    tokenizer.save_pretrained(base)
    BertModel(
        BertConfig(
            vocab_size=len(vocab),
            hidden_size=16,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=32,
        )
    ).save_pretrained(base)
    catalog_path = out / "catalog.json"
    write_json(
        catalog_path,
        {
            "version": "synthetic-smoke",
            "labels": {
                "set": "Set an alarm",
                "cancel": "Cancel an alarm",
            },
        },
    )
    for split in ("train", "validation", "test"):
        (out / f"{split}.jsonl").write_text(
            "\n".join(
                json.dumps(
                    {
                        "sample_id": f"{split}-{i}",
                        "text": text,
                        "label": label,
                    }
                )
                for i, (text, label) in enumerate(
                    [
                        ("set my alarm", "set"),
                        ("cancel my alarm", "cancel"),
                    ]
                )
            )
            + "\n",
            encoding="utf-8",
        )
    model_dir = out / "model"
    with (out / "training.log").open("w", encoding="utf-8") as stream:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "services.train_bert",
                "--train",
                str(out / "train.jsonl"),
                "--validation",
                str(out / "validation.jsonl"),
                "--catalog",
                str(catalog_path),
                "--out",
                str(model_dir),
                "--base-model",
                str(base),
                "--revision",
                "local",
                "--epochs",
                "2",
                "--batch-size",
                "2",
                "--max-length",
                "8",
                "--device",
                args.device,
            ],
            cwd=root,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
        )
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    env = dict(os.environ, MODEL_PATH=str(model_dir), DEVICE=args.device, TORCH_NUM_THREADS="2")
    with (out / "service.log").open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "services.bert_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                "1",
            ],
            cwd=root,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            with httpx.Client(base_url=base_url, trust_env=False, timeout=2) as client:
                deadline = time.monotonic() + 120
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("service exited; see service.log")
                    try:
                        response = client.get("/health")
                        response.raise_for_status()
                        health = response.json()
                        if health.get("ready"):
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError("service did not become ready")
                    time.sleep(0.2)
            if health["model_version"] != metadata["model_version"]:
                raise RuntimeError("unexpected service on selected port")
            runs = []
            for mode in ("quality", "load"):
                config = {
                    "name": f"synthetic-bert-smoke-{mode}",
                    "mode": mode,
                    "dataset": str(out / "test.jsonl"),
                    "catalog": str(catalog_path),
                    "output_dir": str(out / "runs"),
                    "adapter": {"kind": "bert", "base_url": base_url},
                    "warmup": 1,
                    "offered_rps": 5,
                    "duration_s": 2,
                    "max_concurrency": 4,
                    "environment": {
                        "service": health,
                        "model_version": metadata["model_version"],
                        "training_seed": 42,
                        "repeat": 1,
                        "experiment_stage": "smoke",
                        "plan_sha256": "synthetic",
                        "network_note": "loopback smoke",
                    },
                }
                path = out / f"{mode}-config.json"
                write_json(path, config)
                run_dir = asyncio.run(run(path, root))
                records = read_jsonl(run_dir / "requests.jsonl")
                expected = 2 if mode == "quality" else 10
                if len(records) != expected or any(r["status"] != "ok" for r in records):
                    raise RuntimeError(f"{mode} smoke failed; inspect request logs")
                runs.append(run_dir)
            analyze(runs, out / "analysis")
            write_json(
                out / "smoke-result.json",
                {
                    "status": "PASS",
                    "synthetic": True,
                    "device": args.device,
                    "quality_requests": 2,
                    "load_requests": 10,
                    "model_version": metadata["model_version"],
                    "service": health,
                    "note": "Infrastructure validation only; not a MASSIVE accuracy or capacity result",
                },
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    print(f"BERT end-to-end smoke PASS: {out}")


if __name__ == "__main__":
    main()
