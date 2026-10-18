import pytest

from decisionbench.bert_analysis import confirmed_capacities, paired_accuracy, steady_windows
from decisionbench.config import RunConfig
from decisionbench.metrics import request_cost


def test_windows_attribute_slow_completion_to_original_arrival():
    config = RunConfig(
        name="windows",
        mode="load",
        dataset="unused",
        catalog="unused",
        adapter={},
        duration_s=120,
        offered_rps=1,
    )
    rows = [
        {
            "request_id": str(i),
            "sample_id": str(i),
            "status": "ok",
            "prediction": "a",
            "expected_label": "a",
            "scheduled_s": i,
            "dispatch_s": i,
            "completed_s": i + 0.1,
            "scheduler_lag_ms": 0,
            "e2e_latency_ms": 100,
        }
        for i in range(120)
    ]
    rows[59].update(completed_s=61, e2e_latency_ms=2000)
    windows = steady_windows(rows, config, ["a"])
    assert [w["offered_requests"] for w in windows] == [60, 60]
    assert windows[0]["elapsed_s_including_drain"] == 61
    assert windows[1]["elapsed_s_including_drain"] == 60
    assert windows[0]["slo_valid_requests"] == 59
    assert windows[1]["slo_valid_requests"] == 60
    with pytest.raises(ValueError, match="arrival count"):
        steady_windows(rows[:-1], config, ["a"])


def test_capacity_needs_every_formal_repeat_and_window():
    base = {
        "stage": "formal",
        "mode": "load",
        "model_version": "bert:v1",
        "device": "cpu",
        "plan_sha256": "plan",
        "network_note": "local",
        "offered_rps": 1,
        "duration_s": 300,
        "passed": True,
        "windows_passed": True,
        "synthetic": False,
    }
    rows = [{**base, "repeat": i} for i in (1, 2, 3)]
    assert confirmed_capacities(rows)[0]["confirmed"]
    assert not confirmed_capacities(rows[:2])[0]["confirmed"]
    rows[1]["windows_passed"] = False
    assert not confirmed_capacities(rows)[0]["confirmed"]
    rows[1]["windows_passed"] = True
    rows[1]["repeat"] = 1
    assert not confirmed_capacities(rows)[0]["confirmed"]


def test_paired_accuracy_keeps_failed_requests_and_rejects_pooled_repeats():
    rows = [
        {"sample_id": "a", "status": "ok", "expected_label": "a", "prediction": "a"},
        {"sample_id": "b", "status": "timeout", "expected_label": "b", "prediction": None},
    ]
    baseline = [
        {"sample_id": "a", "expected_label": "a", "prediction": "b"},
        {"sample_id": "b", "expected_label": "b", "prediction": "b"},
    ]
    result = paired_accuracy(rows, baseline, "prediction", draws=200)
    assert result["difference"] == 0
    assert result["unique_samples"] == 2
    with pytest.raises(ValueError, match="unique sample"):
        paired_accuracy(rows + rows, baseline, "prediction")


def test_cost_distinguishes_correct_from_slo_correct():
    rows = [
        {"status": "ok", "prediction": "a", "expected_label": "a", "e2e_latency_ms": 100},
        {"status": "ok", "prediction": "a", "expected_label": "a", "e2e_latency_ms": 600},
        {"status": "ok", "prediction": "b", "expected_label": "a", "e2e_latency_ms": 100},
        {"status": "timeout", "prediction": None, "expected_label": "a", "e2e_latency_ms": 1000},
    ]
    result = request_cost(
        rows,
        100,
        {
            "billing": "instance",
            "currency": "TEST",
            "instance_price_per_hour": 36,
        },
        500,
    )
    assert result["total_measured_cost"] == 1
    assert result["cost_per_million_correct"] == 500000
    assert result["cost_per_million_slo_correct"] == 1000000
