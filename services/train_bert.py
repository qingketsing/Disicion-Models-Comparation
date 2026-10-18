"""Train a versioned BERT classifier; native text overlaps are recorded, not removed."""

import argparse
import json
import math
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json
from services.bert_support import classification_metrics, environment_info, overlap_report
from services.common import save_metadata, training_inputs


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("train", "validation", "catalog", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--base-model", default="google-bert/bert-base-uncased")
    parser.add_argument(
        "--revision", required=True, help="HF commit SHA; 'local' only for local models"
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--precision", choices=("fp32", "bf16", "fp16"), default="fp32")
    parser.add_argument("--torch-threads", type=int, default=4)
    parser.add_argument("--text-overlap", choices=("warn", "error"), default="warn")
    parser.add_argument("--full-determinism", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--resume", type=Path, help="An existing checkpoint within this output directory"
    )
    parser.add_argument(
        "--max-steps", type=int, default=-1, help="Use a small value for smoke only"
    )
    args = parser.parse_args(argv)
    for name in (
        "epochs",
        "batch_size",
        "gradient_accumulation_steps",
        "max_length",
        "torch_threads",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"{name} must be positive")
    if not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        parser.error("learning rate must be finite and positive")
    if not math.isfinite(args.weight_decay) or args.weight_decay < 0:
        parser.error("weight decay must be finite and nonnegative")
    if not 0 <= args.warmup_ratio < 1:
        parser.error("warmup ratio must be in [0, 1)")
    if args.max_steps != -1 and args.max_steps < 1:
        parser.error("max steps must be -1 or positive")
    local = Path(args.base_model).is_dir()
    if not local and not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("remote models require an immutable 40-character HF commit SHA")
    if args.device == "cpu" and args.precision != "fp32":
        parser.error("the CPU reference training path uses fp32")
    return args


def main(argv=None):
    args = parse_args(argv)
    catalog, train, valid = training_inputs(
        args.train,
        args.catalog,
        args.validation,
        text_overlap=args.text_overlap,
    )
    labels = list(catalog.labels)
    request = {
        k: str(v.resolve()) if isinstance(v, Path) else v
        for k, v in vars(args).items()
        if k != "resume"
    }
    request["input_sha256"] = {
        name: file_hash(getattr(args, name)) for name in ("train", "validation", "catalog")
    }
    if Path(args.base_model).is_dir():
        request["base_model_files"] = {
            p.relative_to(args.base_model).as_posix(): file_hash(p)
            for p in sorted(Path(args.base_model).rglob("*"))
            if p.is_file()
        }
    request_path = args.out / "training-request.json"
    state_path = args.out / "training-state.json"
    state = {"attempts": []}
    if args.resume:
        if (args.out / "metadata.json").exists():
            raise ValueError("model is already complete; use a new output directory")
        if not args.resume.resolve().is_relative_to((args.out / "checkpoints").resolve()):
            raise ValueError("resume checkpoint must be inside this run's checkpoints directory")
        for name in ("trainer_state.json", "optimizer.pt", "scheduler.pt"):
            if not (args.resume / name).is_file():
                raise ValueError(f"incomplete resume checkpoint: {name}")
        if json.loads(request_path.read_text(encoding="utf-8")) != request:
            raise ValueError(
                "resume parameters or input hashes differ from the frozen training request"
            )
        state = json.loads(state_path.read_text(encoding="utf-8"))
    elif args.out.exists() and any(args.out.iterdir()):
        raise ValueError("output must be empty; use a new version directory or --resume CHECKPOINT")
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(request_path, request)
    write_json(args.out / "overlap-audit.json", overlap_report(train, valid))
    source_dir = args.out / "training-source"
    source_dir.mkdir(exist_ok=True)
    repository = Path(__file__).resolve().parents[1]
    sources = [
        p for folder in ("services", "decisionbench") for p in (repository / folder).glob("*.py")
    ]
    sources += [repository / name for name in ("pyproject.toml", "requirements-bert.lock.txt")]
    for source in sources:
        destination = source_dir / source.relative_to(repository)
        if args.resume and file_hash(destination) != file_hash(source):
            raise ValueError("training source changed; do not resume under different code")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    start = time.perf_counter()
    attempt = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": "running",
        "resume": str(args.resume) if args.resume else None,
    }
    state["attempts"].append(attempt)
    state["state"] = "running"
    write_json(state_path, state)
    try:
        import torch
        from datasets import Dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            DataCollatorWithPadding,
            Trainer,
            TrainingArguments,
            set_seed,
        )

        torch.set_num_threads(args.torch_threads)
        if args.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable; no silent CPU fallback")
        if args.device == "cuda" and torch.cuda.device_count() != 1:
            raise RuntimeError("select one GPU with CUDA_VISIBLE_DEVICES for the single-GPU baseline")
        if args.precision == "bf16" and not torch.cuda.is_bf16_supported():
            raise RuntimeError("BF16 was requested but is unsupported")
        if args.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
        set_seed(args.seed)
        env = environment_info()
        env.update(
            cuda_runtime=torch.version.cuda,
            torch_threads=torch.get_num_threads(),
            device=args.device,
            precision=args.precision,
        )
        if args.resume and (args.out / "environment.json").exists():
            previous_env = json.loads((args.out / "environment.json").read_text(encoding="utf-8"))
            if env != previous_env:
                raise ValueError("environment changed; resume requires the original environment")
        write_json(args.out / "environment.json", env)
        local = Path(args.base_model).is_dir()
        kwargs = {"local_files_only": True} if local else {"revision": args.revision}
        tokenizer = AutoTokenizer.from_pretrained(args.base_model, **kwargs)
        model = AutoModelForSequenceClassification.from_pretrained(
            args.base_model,
            **kwargs,
            num_labels=len(labels),
            id2label=dict(enumerate(labels)),
            label2id={label: i for i, label in enumerate(labels)},
            attn_implementation="eager",
        )
        label_to_id = {label: i for i, label in enumerate(labels)}
        lengths = {}

        def encode(samples, split):
            dataset = Dataset.from_dict(
                {
                    "text": [s.text for s in samples],
                    "labels": [label_to_id[s.label] for s in samples],
                }
            )
            sizes = [
                len(ids)
                for ids in tokenizer(
                    [s.text for s in samples],
                    truncation=False,
                    padding=False,
                )["input_ids"]
            ]
            lengths[split] = {
                "count": len(sizes),
                "max_tokens": max(sizes),
                "truncated_count": sum(n > args.max_length for n in sizes),
            }
            return dataset.map(
                lambda row: tokenizer(row["text"], truncation=True, max_length=args.max_length),
                batched=True,
                remove_columns=["text"],
            )

        def compute_metrics(prediction):
            return classification_metrics(
                prediction.label_ids,
                prediction.predictions.argmax(-1),
                labels,
            )

        trainer = Trainer(
            model=model,
            args=TrainingArguments(
                output_dir=str(args.out / "checkpoints"),
                num_train_epochs=args.epochs,
                max_steps=args.max_steps,
                per_device_train_batch_size=args.batch_size,
                per_device_eval_batch_size=args.batch_size,
                gradient_accumulation_steps=args.gradient_accumulation_steps,
                learning_rate=args.learning_rate,
                weight_decay=args.weight_decay,
                warmup_ratio=args.warmup_ratio,
                lr_scheduler_type="linear",
                optim="adamw_torch",
                max_grad_norm=1.0,
                seed=args.seed,
                data_seed=args.seed,
                full_determinism=args.full_determinism,
                eval_strategy="epoch",
                save_strategy="epoch",
                logging_strategy="epoch",
                save_total_limit=2,
                load_best_model_at_end=True,
                metric_for_best_model="macro_f1",
                greater_is_better=True,
                use_cpu=args.device == "cpu",
                bf16=args.precision == "bf16",
                fp16=args.precision == "fp16",
                dataloader_num_workers=0,
                report_to="none",
                save_safetensors=True,
            ),
            train_dataset=encode(train, "train"),
            eval_dataset=encode(valid, "validation"),
            data_collator=DataCollatorWithPadding(tokenizer),
            compute_metrics=compute_metrics,
            processing_class=tokenizer,
        )
        write_json(args.out / "token-lengths.json", lengths)
        trainer.train(resume_from_checkpoint=str(args.resume) if args.resume else None)
        validation_metrics = trainer.evaluate()
        trainer.save_model(str(args.out))
        tokenizer.save_pretrained(args.out)
        write_json(args.out / "learning-curve.json", trainer.state.log_history)
        attempt.update(state="completed", wall_s=time.perf_counter() - start)
        save_metadata(
            args.out,
            catalog,
            args.train,
            {
                "kind": "bert",
                "seed": args.seed,
                "base_model": args.base_model,
                "revision": args.revision,
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "effective_batch_size": args.batch_size * args.gradient_accumulation_steps,
                "max_length": args.max_length,
                "precision": args.precision,
                "attention_implementation": "eager",
                "text_overlap_policy": args.text_overlap,
                "validation_sha256": file_hash(args.validation),
                "validation_metrics": validation_metrics,
                "selection": "max validation full-catalog macro_f1; earliest checkpoint on ties",
                "best_checkpoint": trainer.state.best_model_checkpoint,
                "best_validation_macro_f1": trainer.state.best_metric,
                "training_wall_s": sum(item.get("wall_s", 0) for item in state["attempts"]),
                "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated()
                if args.device == "cuda"
                else None,
                "synthetic": args.revision == "local" or args.max_steps != -1,
            },
        )
        state["state"] = "completed"
        print(f"Saved BERT: {args.out}", flush=True)
    except BaseException as exc:
        attempt.update(
            state="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
            error_type=type(exc).__name__,
            wall_s=time.perf_counter() - start,
        )
        state["state"] = attempt["state"]
        raise
    finally:
        write_json(state_path, state)


if __name__ == "__main__":
    main()
