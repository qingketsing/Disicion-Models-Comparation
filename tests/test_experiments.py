import asyncio
import csv
import json
import zipfile

import pytest
import yaml

from decisionbench.analysis import analyze, audit_run, independent_quality, paired_bootstrap
from decisionbench.artifacts import file_hash, write_json
from decisionbench.config import RunConfig
from decisionbench.cost_analysis import price_suite
from decisionbench.datasets import load_catalog, load_samples
from decisionbench.protocol import Catalog, Sample
from decisionbench.suite import execution_checks, prepare, run_plan
from decisionbench.variants import scale_variants, write_samples
from scripts.check_qwen_context import check_plan
from scripts.package_experiments import package


@pytest.fixture
def experiment_root(tmp_path):
    directory = tmp_path / "data/normalized/toy"
    directory.mkdir(parents=True)
    labels = {name: f"Select {name}" for name in ("alpha", "beta", "gamma", "delta")}
    rows = [
        Sample(f"{label}-{i}", f"{label} request {i}", label) for label in labels for i in range(4)
    ]
    write_samples(directory / "test.jsonl", rows)
    write_json(directory / "catalog.json", {"version": "toy-v1", "labels": labels})
    write_json(
        directory / "provenance.json",
        {
            "descriptions_reviewed": True,
            "normalized_sha256": {
                name: file_hash(directory / name) for name in ("test.jsonl", "catalog.json")
            },
        },
    )
    spec = {
        "name": "toy-suite",
        "dataset_dir": "data/normalized/toy",
        "cooldown_s": 0,
        "models": {
            name: {
                "adapter": {
                    "kind": "mock",
                    "delay_ms": 0,
                    "rules": {label: label for label in labels},
                },
                "warmup": 1,
            }
            for name in ("qwen", "jev")
        },
        "common": {"max_concurrency": 2},
        "blocks": {
            "main": {"enabled": True, "dataset": "test.jsonl", "repeats": 1},
            "load": {
                "enabled": True,
                "dataset": "test.jsonl",
                "repeats": 1,
                "rates": [20],
                "duration_s": 0.1,
            },
            "scale": {
                "enabled": True,
                "dataset": "test.jsonl",
                "sizes": [2, 3, 4],
                "seeds": [42],
                "samples_per_anchor_class": 2,
            },
        },
    }
    config = tmp_path / "suite.yaml"
    config.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return tmp_path, config, spec


def test_scale_variants_keep_samples_and_nested_catalogs():
    catalog = Catalog("v1", {str(i): f"description {i}" for i in range(6)})
    samples = [
        Sample(f"{label}-{i}", f"text {label} {i}", label)
        for label in catalog.labels
        for i in range(5)
    ]
    rows, catalogs, anchors = scale_variants(samples, catalog, [2, 4, 6], 42, 3)
    assert len(rows) == 6
    assert {s.label for s in rows} == set(anchors)
    assert set(catalogs[2].labels) < set(catalogs[4].labels) < set(catalogs[6].labels)
    assert (rows, catalogs, anchors) == scale_variants(samples, catalog, [2, 4, 6], 42, 3)
    assert (rows, catalogs, anchors) != scale_variants(samples, catalog, [2, 4, 6], 43, 3)
    with pytest.raises(ValueError):
        scale_variants(samples, catalog, [2, 7], 42, 3)
    with pytest.raises(ValueError):
        scale_variants(samples, catalog, [2, 4], 42, 8)


def test_prepare_rejects_unreviewed_or_modified_sources(experiment_root):
    root, config, _ = experiment_root
    provenance = root / "data/normalized/toy/provenance.json"
    data = json.loads(provenance.read_text())
    data["descriptions_reviewed"] = False
    write_json(provenance, data)
    with pytest.raises(ValueError, match="review"):
        prepare(config, root, root / "experiments/bad")
    data["descriptions_reviewed"] = True
    write_json(provenance, data)
    with (root / "data/normalized/toy/test.jsonl").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="changed"):
        prepare(config, root, root / "experiments/bad")


async def test_preview_freeze_and_portability(experiment_root, monkeypatch):
    root, config, _ = experiment_root
    plan = prepare(config, root, root / "experiments/toy")
    data = json.loads(plan.read_text())
    assert len(data["jobs"]) == 10
    for job in data["jobs"]:
        cfg = yaml.safe_load((root / job["config"]).read_text())
        assert not cfg["dataset"].startswith(str(root))
        catalog = load_catalog(root / cfg["catalog"])
        assert load_samples(root / cfg["dataset"], [catalog])

    async def forbidden(*args, **kwargs):
        raise AssertionError("preview must never call the harness")

    monkeypatch.setattr("decisionbench.suite.run", forbidden)
    result = await run_plan(plan, root, ["main"], [], execute=False)
    assert result["remaining_runs"] == 2
    assert not (root / "results").exists()
    target = root / data["jobs"][0]["config"]
    target.write_text(target.read_text() + "\n")
    with pytest.raises(ValueError, match="modified"):
        await run_plan(plan, root, [], [])


async def test_api_budget_checked_before_requests(experiment_root, monkeypatch):
    root, config, spec = experiment_root
    spec["models"]["jev"] = {
        "adapter": {
            "kind": "jev",
            "base_url": "https://unused.invalid",
            "model": "jev-test",
            "api_key_env": "TEST_API_KEY",
        },
        "warmup": 5,
        "environment": {"network_path": "test", "api_quota_rps": 10},
    }
    config.write_text(yaml.safe_dump(spec))
    plan = prepare(config, root, root / "experiments/toy")
    monkeypatch.setenv("TEST_API_KEY", "fake-key")

    async def forbidden(*args, **kwargs):
        raise AssertionError("insufficient budget must not send requests")

    monkeypatch.setattr("decisionbench.suite.run", forbidden)
    preview = await run_plan(plan, root, ["main"], ["jev"])
    assert preview["api_requests_upper_bound_this_invocation"] == 21
    with pytest.raises(ValueError, match="budget"):
        await run_plan(plan, root, ["main"], ["jev"], True, 20)
    assert not (root / "results").exists()
    data = json.loads(plan.read_text())
    for job in data["jobs"]:
        if job["model"] == "jev":
            job["api_requests_upper_bound"] = 0
    write_json(plan, data)
    with pytest.raises(ValueError, match="metadata"):
        await run_plan(plan, root, ["main"], ["jev"], True, 0)


async def test_end_to_end_mock_resume_analysis_and_repricing(experiment_root):
    root, config, _ = experiment_root
    plan = prepare(config, root, root / "experiments/toy")
    with pytest.raises(ValueError, match="baseline"):
        await run_plan(plan, root, ["load"], [], True)
    await run_plan(plan, root, ["main"], [], True)
    await run_plan(plan, root, ["load", "scale"], [], True)
    resumed = await run_plan(plan, root, [], [], True)
    assert resumed["remaining_runs"] == 0
    rows = analyze(plan, root, root / "reports/v1", plots=True)
    assert len(rows) == 10
    assert all(row["synthetic"] for row in rows)
    assert (root / "reports/v1/scale-accuracy.png").exists()
    pairs = list(csv.DictReader((root / "reports/v1/paired-comparisons.csv").open()))
    assert len(pairs) == 4
    assert all(float(row["accuracy_difference_right_minus_left"]) == 0 for row in pairs)
    pricing = {
        "qwen": {
            "billing": "instance",
            "currency": "CNY",
            "instance_price_per_hour": 2,
            "price_source": "synthetic test invoice",
            "price_date": "2026-10-13",
        },
        "jev": {
            "billing": "api",
            "currency": "CNY",
            "input_price_per_million": 1,
            "output_price_per_million": 0,
            "price_source": "synthetic test invoice",
            "price_date": "2026-10-13",
        },
    }
    costs = price_suite(
        plan,
        root,
        pricing,
        root / "reports/costs",
        {
            "hours": 730,
            "utilization": 0.7,
            "training_cost": 0,
            "maintenance_cost": 0,
            "scenarios": [{"name": "toy", "monthly_requests": 1000, "peak_rps": 1}],
        },
        max_slo_qps=10,
    )
    assert len(costs) == 10
    assert not next(c for c in costs if c["model"] == "jev")["usage_complete"]
    repriced = analyze(plan, root, root / "reports/v2")
    assert all(row["cost_source"] == "cost.json" for row in repriced)
    assert (await run_plan(plan, root, [], [], True))["remaining_runs"] == 0


async def test_interruption_requires_explicit_retry(experiment_root, monkeypatch):
    root, config, _ = experiment_root
    plan = prepare(config, root, root / "experiments/toy")

    async def interrupted(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr("decisionbench.suite.run", interrupted)
    with pytest.raises(asyncio.CancelledError):
        await run_plan(plan, root, ["main"], ["qwen"], True)
    index = root / "results/suites" / file_hash(plan) / "index.json"
    assert (
        json.loads(index.read_text())["jobs"]["main-full-seed42-rep1-qwen"]["state"]
        == "interrupted"
    )
    assert not index.with_name("running.lock").exists()
    with pytest.raises(ValueError, match="unfinished"):
        await run_plan(plan, root, ["main"], ["qwen"], True)


async def test_completed_log_tampering_is_detected(experiment_root):
    root, config, _ = experiment_root
    plan = prepare(config, root, root / "experiments/toy")
    await run_plan(plan, root, ["main"], ["qwen"], True)
    index = json.loads((root / "results/suites" / file_hash(plan) / "index.json").read_text())
    entry = index["jobs"]["main-full-seed42-rep1-qwen"]
    directory = root / entry["run_dir"]
    log = directory / "requests.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines()]
    records[0]["expected_label"] = "invented-ground-truth"
    log.write_text("\n".join(json.dumps(row) for row in records))
    with pytest.raises(ValueError, match="modified"):
        await run_plan(plan, root, [], [])
    with pytest.raises(ValueError, match="ground truth"):
        audit_run(directory)


def test_independent_metrics_and_paired_ci():
    records = [
        {"expected_label": "a", "prediction": "a", "status": "ok"},
        {"expected_label": "b", "prediction": None, "status": "timeout"},
    ]
    metrics = independent_quality(records, ["a", "b", "c"])
    assert metrics == {"accuracy": 0.5, "macro_f1": 1 / 3, "macro_f1_supported_classes": 0.5}
    assert paired_bootstrap([1, 1, 1]) == (1, 1, 1)
    assert paired_bootstrap([0, 0, 0]) == (0, 0, 0)


def test_environment_and_api_quota_checks(monkeypatch):
    cfg = RunConfig(
        name="test",
        mode="load",
        dataset="x",
        catalog="x",
        offered_rps=8,
        adapter={"kind": "jev", "api_key_env": "TEST_KEY"},
        environment={"network_path": "test", "api_quota_rps": 4},
    )
    monkeypatch.setenv("TEST_KEY", "fake-secret")
    with pytest.raises(ValueError, match="quota"):
        execution_checks(cfg)
    cfg.offered_rps = 4
    execution_checks(cfg)
    cfg.environment["network_path"] = "TODO"
    with pytest.raises(ValueError, match="metadata"):
        execution_checks(cfg)


def test_upload_package_uses_allowlist(experiment_root):
    root, _, _ = experiment_root
    (root / ".env").write_text("SECRET=never-package")
    (root / ".venv").mkdir()
    (root / ".venv/secret.txt").write_text("not-source")
    (root / "README.md").write_text("test source")
    destination = root / "dist/upload.zip"
    package(root, destination)
    with zipfile.ZipFile(destination) as archive:
        assert "README.md" in archive.namelist()
        assert ".env" not in archive.namelist()
        assert not any(".venv" in name for name in archive.namelist())


def test_context_check_reuses_non_thinking_prompt(experiment_root):
    root, config, spec = experiment_root
    spec["models"]["qwen"]["adapter"] = {
        "kind": "qwen",
        "base_url": "http://unused.invalid",
        "model": "qwen-test",
        "max_tokens": 64,
    }
    config.write_text(yaml.safe_dump(spec))
    plan = prepare(config, root, root / "experiments/toy")

    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs == {
                "tokenize": True,
                "add_generation_prompt": True,
                "enable_thinking": False,
            }
            assert len(messages) == 2
            assert "Catalog:" in messages[0]["content"]
            return list(range(100))

    checks = check_plan(plan, root, Tokenizer(), 164)
    assert len(checks) == 4  # main/load share the same input/catalog pair.
    assert all(c["fits"] for c in checks)
    assert not any(c["fits"] for c in check_plan(plan, root, Tokenizer(), 163))


def test_description_variants_preserve_label_order(experiment_root):
    root, config, spec = experiment_root
    mappings = {}
    for variant in ("brief", "detailed"):
        mapping_path = root / f"{variant}.json"
        write_json(
            mapping_path,
            {label: f"{variant} {label}" for label in ("delta", "gamma", "beta", "alpha")},
        )
        mappings[variant] = mapping_path.name
    spec["blocks"] = {
        "descriptions": {
            "enabled": True,
            "dataset": "test.jsonl",
            "repeats": 1,
            "mappings": mappings,
        }
    }
    config.write_text(yaml.safe_dump(spec))
    plan = prepare(config, root, root / "experiments/toy")
    for job in json.loads(plan.read_text())["jobs"]:
        cfg = yaml.safe_load((root / job["config"]).read_text())
        assert list(load_catalog(root / cfg["catalog"]).labels) == [
            "alpha",
            "beta",
            "gamma",
            "delta",
        ]


def test_default_matrix_and_api_request_budget(tmp_path):
    # Synthetic inputs are only for a planning test; adapters are never constructed.
    repo = __import__("pathlib").Path(__file__).resolve().parents[1]
    spec = yaml.safe_load((repo / "configs/experiment-suite.yaml").read_text(encoding="utf-8"))
    directory = tmp_path / spec["dataset_dir"]
    directory.mkdir(parents=True)
    labels = {f"intent-{i}": f"Choose synthetic intent {i}" for i in range(60)}
    rows = [
        Sample(f"{label}-{i}", f"Synthetic test input {label} {i}", label)
        for label in labels
        for i in range(20)
    ]
    write_samples(directory / "test.jsonl", rows)
    write_samples(directory / "checkpoint-300.jsonl", rows[:300])
    write_json(directory / "catalog.json", {"version": "synthetic-only", "labels": labels})
    write_json(directory / "provenance.json", {"descriptions_reviewed": True, "synthetic": True})
    config = tmp_path / "suite.yaml"
    config.write_text(yaml.safe_dump(spec), encoding="utf-8")
    plan = prepare(config, tmp_path, tmp_path / "experiments/budget")
    jobs = json.loads(plan.read_text())["jobs"]
    assert len(jobs) == 50
    assert sum(j["api_requests_upper_bound"] for j in jobs) == 3 * len(rows) + 7625
