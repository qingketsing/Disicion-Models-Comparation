import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from decisionbench.artifacts import file_hash
from decisionbench.protocol import Catalog
from services.common import catalog_signature


class CatalogInput(BaseModel):
    version: str
    labels: dict[str, str]


class PredictInput(BaseModel):
    sample_id: str
    text: str = Field(min_length=1)
    catalog: CatalogInput


def create_app(kind):
    registry = CollectorRegistry()
    requests = Counter(
        "decisionbench_predictions_total", "Prediction requests", ["status"], registry=registry
    )
    latency = Histogram(
        "decisionbench_service_seconds", "Service time including lock queue", registry=registry
    )
    lock = threading.Lock()
    state = {}

    @asynccontextmanager
    async def lifespan(app):
        directory = Path(os.environ.get("MODEL_PATH", f"models/{kind}"))
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        for name, expected_hash in metadata["artifact_files"].items():
            if file_hash(directory / name) != expected_hash:
                raise ValueError("model artifact hash mismatch")
        state["metadata"] = metadata
        if kind == "classic":
            from joblib import load

            state["model"] = load(directory / "model.joblib")
        else:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            torch.set_num_threads(int(os.environ.get("TORCH_NUM_THREADS", "4")))
            device = os.environ.get("DEVICE", "cpu")
            if device not in {"cpu", "cuda"}:
                raise ValueError("DEVICE must be cpu or cuda")
            if device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA service requested but CUDA is unavailable")
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            model = (
                AutoModelForSequenceClassification.from_pretrained(
                    directory,
                    local_files_only=True,
                    attn_implementation=metadata.get("attention_implementation", "eager"),
                )
                .to(device)
                .eval()
            )
            if [model.config.id2label[i] for i in range(model.config.num_labels)] != metadata[
                "labels"
            ]:
                raise ValueError("model label mapping differs from artifact metadata")
            state.update(
                torch=torch,
                device=device,
                tokenizer=AutoTokenizer.from_pretrained(directory, local_files_only=True),
                model=model,
                torch_threads=torch.get_num_threads(),
                precision="fp32",
                cuda_runtime=torch.version.cuda,
            )
        yield
        state.clear()

    app = FastAPI(title=f"DecisionBench {kind}", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {
            "ready": bool(state),
            "kind": kind,
            "model_version": state.get("metadata", {}).get("model_version"),
            "device": state.get("device", "cpu"),
            "torch_threads": state.get("torch_threads"),
            "precision": state.get("precision"),
            "cuda_runtime": state.get("cuda_runtime"),
            "synthetic": state.get("metadata", {}).get("synthetic", False),
        }

    @app.get("/metadata")
    def metadata():
        return state["metadata"]

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")

    @app.post("/predict")
    def predict(body: PredictInput):
        catalog = Catalog(body.catalog.version, body.catalog.labels)
        if catalog_signature(catalog) != state["metadata"]["catalog_signature"]:
            requests.labels("catalog_mismatch").inc()
            raise HTTPException(409, "Catalog differs from trained artifact; retrain explicitly")
        started = time.perf_counter()
        try:
            # One model instance, serialized inference. Threadpool queues are part of E2E latency.
            with lock:
                model = state["model"]
                if kind == "classic":
                    label = str(model.predict([body.text])[0])
                    margins = model.decision_function([body.text])[0]
                    classes = list(model.classes_)
                    if len(classes) == 2:
                        margins = [-float(margins), float(margins)]
                    scores = dict(zip(classes, map(float, margins)))
                    score_type = "svm_margin_uncalibrated"
                else:
                    torch = state["torch"]
                    inputs = state["tokenizer"](
                        body.text,
                        return_tensors="pt",
                        truncation=True,
                        max_length=state["metadata"]["max_length"],
                    )
                    inputs = {k: v.to(state["device"]) for k, v in inputs.items()}
                    with torch.inference_mode():
                        probabilities = model(**inputs).logits.softmax(-1)[0].cpu().tolist()
                    labels = [model.config.id2label[i] for i in range(len(probabilities))]
                    scores = dict(zip(labels, probabilities))
                    label = labels[max(range(len(probabilities)), key=probabilities.__getitem__)]
                    score_type = "softmax_uncalibrated"
            requests.labels("ok").inc()
            return {
                "label": label,
                "scores": scores,
                "score_type": score_type,
                "confidence": None,
                "model_version": state["metadata"]["model_version"],
            }
        finally:
            latency.observe(time.perf_counter() - started)

    return app
