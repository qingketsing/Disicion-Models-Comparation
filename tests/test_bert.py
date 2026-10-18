import json
from pathlib import Path

import pytest

from decisionbench.artifacts import file_hash, write_json
from decisionbench.protocol import Sample
from services.bert_support import classification_metrics, overlap_report
from services.common import training_inputs


def tiny_inputs(tmp_path):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from transformers import BertConfig, BertModel, BertTokenizerFast

    base = tmp_path / "base"
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
            max_position_embeddings=32,
        )
    ).save_pretrained(base)
    catalog = tmp_path / "catalog.json"
    write_json(
        catalog,
        {
            "version": "tiny",
            "labels": {
                "set": "Set alarm",
                "cancel": "Cancel alarm",
                "missing": "No validation support",
            },
        },
    )
    train, validation = tmp_path / "train.jsonl", tmp_path / "validation.jsonl"
    for path, prefix in ((train, "train"), (validation, "valid")):
        path.write_text(
            "\n".join(
                json.dumps({"sample_id": f"{prefix}-{i}", "text": text, "label": label})
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
    out = tmp_path / "trained"
    command = [
        "--train",
        str(train),
        "--validation",
        str(validation),
        "--catalog",
        str(catalog),
        "--out",
        str(out),
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
        "cpu",
        "--torch-threads",
        "2",
    ]
    return command, out, train, validation, catalog


def test_metrics_keep_unsupported_classes_in_macro_f1():
    scores = classification_metrics([0, 1], [0, 1], ["set", "cancel", "missing"])
    assert scores == {"accuracy": 1.0, "macro_f1": 2 / 3, "macro_f1_supported": 1.0}


def test_overlap_audit_retains_native_samples():
    train = [Sample("a", "same text", "set"), Sample("b", "other", "cancel")]
    valid = [Sample("c", "same text", "set")]
    report = overlap_report(train, valid)
    assert report["exact_shared_texts"] == 1
    assert report["train_size"] == 2
    assert report["validation_size"] == 1


def test_overlap_warning_does_not_disable_id_validation(tmp_path):
    catalog = tmp_path / "catalog.json"
    write_json(catalog, {"version": "v1", "labels": {"a": "a"}})
    train, valid = tmp_path / "train.jsonl", tmp_path / "valid.jsonl"
    train.write_text('{"sample_id":"train","text":"same","label":"a"}\n')
    valid.write_text('{"sample_id":"valid","text":"same","label":"a"}\n')
    with pytest.warns(UserWarning):
        _, training, validation = training_inputs(train, catalog, valid, text_overlap="warn")
    assert len(training) == len(validation) == 1
    with pytest.raises(ValueError, match="texts overlap"):
        training_inputs(train, catalog, valid)
    valid.write_text(train.read_text())
    with pytest.raises(ValueError, match="sample IDs overlap"):
        training_inputs(train, catalog, valid, text_overlap="warn")


def test_real_tiny_training_best_checkpoint_and_http(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from services.server import create_app
    from services.train_bert import main

    command, out, _, _, catalog_path = tiny_inputs(tmp_path)
    with pytest.warns(UserWarning, match="overlap"):
        main(command)
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["synthetic"] is True
    assert metadata["text_overlap_policy"] == "warn"
    assert metadata["max_length"] == 8
    history = json.loads((out / "learning-curve.json").read_text())
    epochs = [r for r in history if "eval_macro_f1" in r]
    assert metadata["best_validation_macro_f1"] == max(r["eval_macro_f1"] for r in epochs)
    assert file_hash(out / "model.safetensors") == file_hash(
        Path(metadata["best_checkpoint"]) / "model.safetensors"
    )
    for name, expected in metadata["artifact_files"].items():
        assert "\\" not in name
        assert file_hash(out / name) == expected
    assert "catalog.json" in metadata["artifact_files"]
    assert not any(name.startswith("checkpoints/") for name in metadata["artifact_files"])
    monkeypatch.setenv("MODEL_PATH", str(out))
    monkeypatch.setenv("DEVICE", "cpu")
    catalog = json.loads(catalog_path.read_text())
    with TestClient(create_app("bert")) as client:
        assert client.get("/health").json()["precision"] == "fp32"
        payload = {"sample_id": "heldout", "text": "set my alarm " * 20, "catalog": catalog}
        response = client.post("/predict", json=payload)
        assert response.status_code == 200
        result = response.json()
        assert set(result["scores"]) == set(catalog["labels"])
        assert sum(result["scores"].values()) == pytest.approx(1, abs=1e-6)
        assert result["model_version"] == metadata["model_version"]
        assert result["confidence"] is None
        # max_length=8 leaves six content tokens; both texts produce identical tokens.
        payload["text"] = "set my alarm set my alarm"
        assert client.post("/predict", json=payload).json()["scores"] == result["scores"]
        payload["catalog"]["labels"]["new"] = "new intent"
        assert client.post("/predict", json=payload).status_code == 409
    # Both a swapped label map and altered weight/config files must be rejected at startup.
    metadata["labels"] = list(reversed(metadata["labels"]))
    write_json(out / "metadata.json", metadata)
    with pytest.raises(ValueError, match="label mapping"):
        with TestClient(create_app("bert")):
            pass
    metadata["labels"].reverse()
    write_json(out / "metadata.json", metadata)
    with (out / "config.json").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="artifact hash"):
        with TestClient(create_app("bert")):
            pass


def test_resume_after_saved_checkpoint(tmp_path, monkeypatch):
    pytest.importorskip("transformers")
    from transformers import Trainer

    from services.train_bert import main

    command, out, _, _, _ = tiny_inputs(tmp_path)
    original = Trainer._save_checkpoint

    def save_then_interrupt(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("injected interruption after checkpoint")

    monkeypatch.setattr(Trainer, "_save_checkpoint", save_then_interrupt)
    with pytest.raises(RuntimeError, match="injected interruption"), pytest.warns(UserWarning):
        main(command)
    checkpoint = next((out / "checkpoints").glob("checkpoint-*"))
    assert json.loads((out / "training-state.json").read_text())["state"] == "failed"
    monkeypatch.setattr(Trainer, "_save_checkpoint", original)
    with pytest.warns(UserWarning):
        main([*command, "--resume", str(checkpoint)])
    state = json.loads((out / "training-state.json").read_text())
    assert state["state"] == "completed"
    assert [a["state"] for a in state["attempts"]] == ["failed", "completed"]
