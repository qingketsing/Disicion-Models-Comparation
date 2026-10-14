import json
from pathlib import Path

import httpx
import pytest

from decisionbench.adapters import BaseAdapter, JevAdapter, MockAdapter, QwenAdapter
from decisionbench.cli import run
from decisionbench.config import RunConfig
from decisionbench.datasets import load_catalog, load_samples
from decisionbench.metrics import monthly_tco, quality_metrics, request_cost, summarize
from decisionbench.protocol import Catalog, Decision, Sample
from decisionbench.runners import load, measure, quality

CATALOG = Catalog("v1", {"alarm_set": "Create alarm", "alarm_cancel": "Cancel alarm"})
SAMPLES = [Sample("1", "alarm", "alarm_set"), Sample("2", "cancel alarm", "alarm_cancel")]


@pytest.mark.parametrize("total", [0.99, 1.0, 1.01])
def test_probability_sum_accepts_inclusive_one_percent_boundary(total):
    Decision(
        "alarm_set", "provider", {"alarm_set": total / 2, "alarm_cancel": total / 2},
        "provider_probability",
    ).validate(CATALOG)


@pytest.mark.parametrize("total", [0.989, 1.011])
def test_probability_sum_rejects_values_outside_one_percent(total):
    with pytest.raises(ValueError, match="probabilities do not sum to 1"):
        Decision(
            "alarm_set", "provider", {"alarm_set": total / 2, "alarm_cancel": total / 2},
            "provider_probability",
        ).validate(CATALOG)


def config(**kwargs):
    return RunConfig(
        **{
            "name": "test",
            "mode": "quality",
            "dataset": "test.jsonl",
            "catalog": "catalog.json",
            "adapter": {"kind": "mock"},
            **kwargs,
        }
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"offered_rps": 0},
        {"duration_s": float("nan")},
        {"max_concurrency": 0},
        {"warmup": -1},
        {"mode": "unknown"},
        {"timeout_s": -1},
        {"mode": "dynamic", "stages": [{"at_s": 1, "catalog": "x"}]},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        config(**kwargs)


async def test_quality_does_not_expose_ground_truth():
    class InspectAdapter(BaseAdapter):
        async def predict(self, sample, catalog):
            assert not hasattr(sample, "label")
            return Decision("alarm_set", "test")

    rows = []
    await quality(InspectAdapter(), SAMPLES, CATALOG, config(), rows.append)
    summary = summarize(rows, config(), 1, CATALOG.labels)
    assert summary["quality"]["accuracy"] == 0.5
    assert len({r["request_id"] for r in rows}) == 2
    assert all(r["status"] == "ok" for r in rows)


async def test_open_loop_records_overload_and_slo_failure():
    c = config(
        mode="load",
        offered_rps=40,
        duration_s=0.25,
        max_concurrency=1,
        slo_ms=10,
        timeout_s=1,
        max_scheduler_lag_ms=100,
    )
    rows = []
    elapsed = await load(MockAdapter(delay_ms=120), SAMPLES, [(0, CATALOG)], c, rows.append)
    assert len(rows) == 10  # Arrival count does not shrink to server capacity.
    assert len({r["request_id"] for r in rows}) == 10
    assert any(r["status"] == "client_overload" for r in rows)
    assert any(r["status"] == "ok" for r in rows)
    assert elapsed >= c.duration_s
    summary = summarize(rows, c, elapsed, CATALOG.labels)
    assert summary["goodput_qps"] == 0
    assert not summary["slo_capacity_candidate"]
    assert summary["attempted_requests"] < summary["offered_requests"]


async def test_total_deadline_includes_scheduler_delay():
    import time

    now = time.perf_counter()
    row = await measure(
        MockAdapter(delay_ms=1), SAMPLES[0], CATALOG, config(timeout_s=0.01), now, now - 0.02
    )
    assert row["status"] == "timeout"
    assert row["e2e_latency_ms"] >= 20


async def test_timeout_is_preserved():
    import time

    now = time.perf_counter()
    row = await measure(
        MockAdapter(delay_ms=100), SAMPLES[0], CATALOG, config(timeout_s=0.01), now, now
    )
    assert row["status"] == "timeout"


def test_quality_errors_are_false_negatives():
    rows = [
        {"expected_label": "a", "prediction": "a", "status": "ok"},
        {"expected_label": "b", "prediction": None, "status": "timeout"},
    ]
    result = quality_metrics(rows, {"a", "b"})
    assert result["accuracy"] == 0.5
    assert result["accuracy_successful_only"] == 1
    assert result["macro_f1"] == 0.5


def test_instance_and_api_cost_denominators():
    rows = [
        {"status": "ok", "e2e_latency_ms": 10, "input_tokens": 100, "output_tokens": 20},
        {
            "status": "invalid_output",
            "e2e_latency_ms": 10,
            "input_tokens": 200,
            "output_tokens": 30,
        },
    ]
    result = request_cost(rows, 3600, {"currency": "USD", "instance_price_per_hour": 2}, 20)
    assert result["total_measured_cost"] == 2
    assert result["cost_per_million_slo_valid"] == 2_000_000
    result = request_cost(
        rows,
        1,
        {
            "billing": "api",
            "currency": "USD",
            "input_price_per_million": 1,
            "output_price_per_million": 0,
        },
        20,
    )
    assert result["total_measured_cost"] == pytest.approx(0.0003)
    assert result["usage_complete"]
    rows.append({"status": "timeout"})
    assert not request_cost(rows, 1, result["pricing"], 20)["usage_complete"]


def test_tco_accounts_for_peak_and_headroom():
    assert monthly_tco(1_000_000, 20, 10, 2, utilization=0.7)["replicas"] == 3
    with pytest.raises(ValueError, match="peak"):
        monthly_tco(1_000_000, 0.001, 10, 2)


async def mock_http(adapter, response, assert_request=None, status=200):
    await adapter.client.aclose()

    def handler(request):
        if assert_request:
            assert_request(json.loads(request.content))
        return httpx.Response(status, json=response, headers={"x-request-id": "provider-1"})

    adapter.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_jev_official_choice_contract_and_confidence(monkeypatch):
    monkeypatch.setenv("TEST_JEV_KEY", "fake-secret")
    adapter = JevAdapter(
        base_url="https://api.typesafe.ai", model="jev-1.13.0", api_key_env="TEST_JEV_KEY"
    )

    def inspect(body):
        assert body["questions"]["intent"]["criteria"] == CATALOG.labels
        assert body["state"] == "alarm"
        assert "label" not in body

    await mock_http(
        adapter,
        {
            "model": "jev-1.13.0",
            "answers": {
                "intent": {
                    "choice": "alarm_set",
                    "probabilities": {"alarm_set": 0.8, "alarm_cancel": 0.2},
                    "confidence": 0.6,
                }
            },
            "usage": {"input_tokens": 123, "output_tokens": 10},
        },
        inspect,
    )
    try:
        result = await adapter.predict(SAMPLES[0].model_input(), CATALOG)
        assert result.confidence == 0.6
        assert result.scores["alarm_set"] == 0.8
        assert result.input_tokens == 123
    finally:
        await adapter.close()


async def test_qwen_schema_tracks_active_catalog_and_still_rejects_bad_server_output():
    adapter = QwenAdapter(base_url="http://worker", model="qwen", constrain_labels=True)

    def inspect(body):
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["label"]["enum"] == list(CATALOG.labels)
        assert schema["additionalProperties"] is False

    await mock_http(
        adapter,
        {
            "choices": [
                {"message": {"content": '{"label":"outside_catalog"}'}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 123, "completion_tokens": 8},
        },
        inspect,
    )
    try:
        from decisionbench.adapters import InvalidOutput

        with pytest.raises(InvalidOutput):
            await adapter.predict(SAMPLES[0].model_input(), CATALOG)
    finally:
        await adapter.close()


@pytest.mark.parametrize(
    "content,finish,status",
    [
        ('{"label":"alarm_set"}', "stop", "ok"),
        ('```json\n{"label":"alarm_set"}\n```', "stop", "ok"),
        ('{"label":"unknown"}', "stop", "invalid_output"),
        ("alarm_set", "stop", "invalid_output"),
        ('{"label":"alarm_set"}', "length", "invalid_output"),
        ('{"label":[]}', "stop", "invalid_output"),
        ('{"label":NaN}', "stop", "invalid_output"),
    ],
)
async def test_qwen_parsing_preserves_billed_usage(content, finish, status):
    import time

    adapter = QwenAdapter(base_url="http://worker", model="qwen")
    await mock_http(
        adapter,
        {
            "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 20},
        },
    )
    try:
        now = time.perf_counter()
        row = await measure(adapter, SAMPLES[0], CATALOG, config(), now, now)
        assert row["status"] == status
        assert row["input_tokens"] == 123
        assert row["confidence"] is None
    finally:
        await adapter.close()


async def test_http_errors_are_logged():
    import time

    adapter = QwenAdapter(base_url="http://worker", model="qwen")
    await mock_http(adapter, {"error": "rate limited"}, status=429)
    try:
        now = time.perf_counter()
        row = await measure(adapter, SAMPLES[0], CATALOG, config(), now, now)
        assert row["status"] == "http_error"
        assert row["http_status"] == 429
    finally:
        await adapter.close()


def test_duplicate_dataset_ids_rejected(tmp_path):
    path = tmp_path / "test.jsonl"
    row = {"sample_id": "1", "text": "alarm", "label": "alarm_set"}
    path.write_text((json.dumps(row) + "\n") * 2)
    with pytest.raises(ValueError, match="duplicate"):
        load_samples(path, [CATALOG])


async def test_run_artifacts_can_recompute_summary(tmp_path):
    import shutil

    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "data", tmp_path / "data")
    shutil.copytree(root / "configs", tmp_path / "configs")
    output = await run(tmp_path / "configs/smoke-quality.yaml", tmp_path)
    manifest = json.loads((output / "manifest.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    rows = [json.loads(line) for line in (output / "requests.jsonl").read_text().splitlines()]
    assert manifest["state"] == "completed"
    assert manifest["synthetic"]
    assert (output / "source/decisionbench/runners.py").exists()
    catalog = load_catalog(output / "inputs/catalog-0.json")
    recomputed = summarize(rows, config(), manifest["elapsed_s"], catalog.labels)
    assert recomputed["quality"] == summary["quality"]
    assert len(rows) == 6
    assert len((output / "warmup_requests.jsonl").read_text().splitlines()) == 2


async def test_dynamic_catalog_uses_scheduled_arrival():
    rows = []
    changed = Catalog("v2", {**CATALOG.labels, "music_play": "Play music"})
    c = config(
        mode="dynamic",
        offered_rps=20,
        duration_s=0.2,
        stages=[{"at_s": 0, "catalog": "a"}, {"at_s": 0.1, "catalog": "b"}],
    )
    await load(MockAdapter(), SAMPLES, [(0, CATALOG), (0.1, changed)], c, rows.append)
    assert len(rows) == 4
    for row in rows:
        assert row["catalog_version"] == ("v1" if row["scheduled_s"] < 0.1 - 1e-6 else "v2")
