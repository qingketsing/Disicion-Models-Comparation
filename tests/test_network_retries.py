import time

import httpx
import pytest

from decisionbench.adapters import BaseAdapter
from decisionbench.config import RunConfig
from decisionbench.metrics import request_cost, summarize
from decisionbench.protocol import Catalog, Decision, Sample
from decisionbench.runners import measure

CATALOG = Catalog("test", {"a": "label a"})
SAMPLE = Sample("id", "text", "a")


def config(**options):
    return RunConfig(
        name="retry-test",
        mode="quality",
        dataset="test",
        catalog="test",
        adapter={"kind": "mock"},
        network_retries=3,
        network_retry_backoff_s=0,
        **options,
    )


class FlakyAdapter(BaseAdapter):
    def __init__(self, failures, error=None):
        self.failures = failures
        self.calls = 0
        self.error = error or httpx.RemoteProtocolError("do not persist secret-bearing text")

    async def predict(self, sample, catalog):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return Decision("a", "test", input_tokens=20, output_tokens=1)


async def run(adapter, cfg):
    now = time.perf_counter()
    return await measure(adapter, SAMPLE, CATALOG, cfg, now, now)


async def test_three_additional_attempts_can_recover_and_cost_is_lower_bound():
    adapter = FlakyAdapter(3)
    cfg = config()
    row = await run(adapter, cfg)
    assert row["status"] == "ok" and adapter.calls == 4
    assert [a["status"] for a in row["network_attempts"]] == [
        "network_error",
        "network_error",
        "network_error",
        "response_received",
    ]
    assert all(a["completed_s"] >= a["started_s"] for a in row["network_attempts"])
    assert "secret-bearing" not in str(row)
    cost = request_cost(
        [row],
        1,
        {
            "billing": "api",
            "currency": "USD",
            "input_price_per_million": 1,
            "output_price_per_million": 0,
        },
        500,
    )
    assert cost["total_measured_cost"] == 20 / 1_000_000
    assert cost["usage_complete"] is False
    assert summarize([row], cfg, 1, CATALOG.labels)["network_retry"]["recovered_requests"] == 1


async def test_exhausted_retries_remain_failure():
    adapter = FlakyAdapter(10)
    row = await run(adapter, config())
    assert adapter.calls == 4
    assert row["status"] == "network_error"
    assert len(row["network_attempts"]) == 4
    assert all(a["error_type"] == "RemoteProtocolError" for a in row["network_attempts"])


async def test_http_and_invalid_response_are_not_retried():
    response = httpx.Response(429, request=httpx.Request("POST", "https://test.invalid"))
    adapter = FlakyAdapter(
        10, httpx.HTTPStatusError("rate limit", request=response.request, response=response)
    )
    row = await run(adapter, config())
    assert adapter.calls == 1 and row["status"] == "http_error"
    adapter = FlakyAdapter(10, ValueError("bad output"))
    row = await run(adapter, config())
    assert adapter.calls == 1 and row["status"] == "invalid_output"


async def test_transport_timeout_retries_but_total_deadline_is_not_reset():
    adapter = FlakyAdapter(2, httpx.ReadTimeout("transport timeout"))
    row = await run(adapter, config())
    assert row["status"] == "ok" and adapter.calls == 3
    cfg = config(timeout_s=0.01)
    cfg.network_retry_backoff_s = 0.02
    adapter = FlakyAdapter(10)
    started = time.perf_counter()
    row = await run(adapter, cfg)
    assert adapter.calls == 1 and row["status"] == "network_error"
    assert time.perf_counter() - started < 0.1


async def test_backoff_included_in_e2e_latency_and_slo():
    cfg = config(slo_ms=1)
    cfg.network_retry_backoff_s = 0.02
    row = await run(FlakyAdapter(1), cfg)
    assert row["status"] == "ok" and row["e2e_latency_ms"] >= 20
    assert summarize([row], cfg, 1, CATALOG.labels)["slo_valid_requests"] == 0


@pytest.mark.parametrize("retries", [-1, 4, True, 1.5])
def test_invalid_retry_limit(retries):
    with pytest.raises(ValueError, match="network_retries"):
        RunConfig(
            name="test",
            mode="quality",
            dataset="x",
            catalog="x",
            adapter={"kind": "mock"},
            network_retries=retries,
        )
