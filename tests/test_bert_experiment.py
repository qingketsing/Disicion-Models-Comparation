import copy
import json
from pathlib import Path

import pytest
import yaml

from decisionbench.artifacts import file_hash, write_json
from scripts import bert_experiment


def spec():
    root = Path(__file__).resolve().parents[1]
    return yaml.safe_load((root / "configs/bert-experiment.yaml").read_text(encoding="utf-8"))


def test_default_plan_retains_native_splits_and_all_training_seeds():
    config = spec()
    bert_experiment.validate_spec(config)
    assert config["training"]["text_overlap"] == "warn"
    assert config["seeds"] == [42, 43, 44]
    assert config["measurement"]["formal_duration_s"] == 300


def test_frozen_plan_checks_source_and_data_with_portable_source_newlines(tmp_path, monkeypatch):
    monkeypatch.setattr(bert_experiment, "ROOT", tmp_path)
    source = tmp_path / "source.py"
    data = tmp_path / "data.jsonl"
    source.write_bytes(b"x = 1\r\n")
    data.write_bytes(b'{"text":"hello"}\n')
    config = spec()
    config["source_sha256"] = {"source.py": bert_experiment.source_digest(source)}
    config["data_sha256"] = {"data.jsonl": file_hash(data)}
    plan = tmp_path / "plan.json"
    write_json(plan, config)
    write_json(plan.with_suffix(".sha256.json"), {"plan_sha256": file_hash(plan)})
    source.write_bytes(b"x = 1\n")
    assert bert_experiment.read_plan(plan)["seeds"] == [42, 43, 44]
    data.write_bytes(b'{"text":"changed"}\n')
    with pytest.raises(ValueError, match="data_sha256"):
        bert_experiment.read_plan(plan)
    plan.write_text(json.dumps({**config, "seeds": [99]}))
    with pytest.raises(ValueError, match="plan hash"):
        bert_experiment.read_plan(plan)


def test_plan_rejects_invalid_parameters_before_training():
    original = spec()
    changed = copy.deepcopy(original)
    changed["seeds"] = [42, 42]
    with pytest.raises(ValueError, match="unique"):
        bert_experiment.validate_spec(changed)
    changed = copy.deepcopy(original)
    changed["data_dir"] = "../outside"
    with pytest.raises(ValueError, match="relative"):
        bert_experiment.validate_spec(changed)
    changed = copy.deepcopy(original)
    changed["training"]["batch_size"] = 0
    with pytest.raises(SystemExit):
        bert_experiment.validate_spec(changed)


def test_formal_evaluation_rejects_synthetic_service_before_requests(tmp_path, monkeypatch):
    from argparse import Namespace

    monkeypatch.setattr(bert_experiment, "ROOT", tmp_path)
    config = spec()
    data = tmp_path / config["data_dir"]
    data.mkdir(parents=True)
    write_json(data / "catalog.json", {"version": "v1", "labels": {"a": "a"}})
    monkeypatch.setattr(
        bert_experiment,
        "service_metadata",
        lambda _: (
            {"ready": True, "kind": "bert", "synthetic": True},
            {},
        ),
    )
    with pytest.raises(ValueError, match="non-synthetic"):
        bert_experiment.evaluate(Namespace(base_url="http://unused"), config)
