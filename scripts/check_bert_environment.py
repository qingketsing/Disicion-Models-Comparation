"""Verify an actual BERT forward/backward step, without downloading model weights."""

import argparse
import json
from pathlib import Path

from decisionbench.artifacts import write_json
from services.bert_support import environment_info


def check(device):
    info = environment_info()
    try:
        import torch
        from transformers import BertConfig, BertForSequenceClassification

        torch.set_num_threads(2)
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA unavailable; check the NVIDIA driver and the selected torch wheel"
            )
        torch.manual_seed(42)
        model = BertForSequenceClassification(
            BertConfig(
                vocab_size=32,
                hidden_size=32,
                num_hidden_layers=1,
                num_attention_heads=2,
                intermediate_size=64,
                num_labels=3,
                attn_implementation="eager",
            )
        ).to(device)
        tokens = torch.randint(0, 32, (2, 16), device=device)
        result = model(
            input_ids=tokens,
            attention_mask=torch.ones_like(tokens),
            labels=torch.tensor([0, 1], device=device),
        )
        result.loss.backward()
        torch.optim.AdamW(model.parameters(), lr=2e-5).step()
        if not torch.isfinite(result.loss):
            raise RuntimeError("BERT smoke loss is not finite")
        if device == "cuda":
            torch.cuda.synchronize()
        info.update(
            status="PASS",
            device=device,
            cuda_runtime=torch.version.cuda,
            smoke_loss=float(result.loss.detach().cpu()),
            synthetic=True,
        )
        if device == "cuda":
            info.update(
                gpu_name=torch.cuda.get_device_name(),
                capability=list(torch.cuda.get_device_capability()),
                bf16_supported=torch.cuda.is_bf16_supported(),
            )
    except Exception as exc:
        info.update(status="FAIL", device=device, error_type=type(exc).__name__, error=str(exc))
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    info = check(args.device)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, info)
    print(json.dumps(info, indent=2))
    if info["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
