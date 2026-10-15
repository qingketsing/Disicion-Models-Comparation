import asyncio
import math
import random
import time
import uuid
from dataclasses import asdict

import httpx

from decisionbench.adapters import BaseAdapter, InvalidOutput
from decisionbench.config import RunConfig
from decisionbench.protocol import Catalog, Sample


def base_record(sample, catalog, origin, scheduled, phase):
    return {
        "request_id": str(uuid.uuid4()),
        "sample_id": sample.sample_id,
        "expected_label": sample.label,
        "catalog_version": catalog.version,
        "reject_label": catalog.reject_label,
        "phase": phase,
        "scheduled_s": scheduled - origin,
        "dispatch_s": None,
        "completed_s": None,
        "scheduler_lag_ms": None,
        "service_latency_ms": None,
        "e2e_latency_ms": None,
        "status": "pending",
        "http_status": None,
        "error_type": None,
        "prediction": None,
        "model_version": None,
        "scores": {},
        "score_type": None,
        "confidence": None,
        "input_tokens": None,
        "output_tokens": None,
        "provider_request_id": None,
    }


def attach_decision(record, decision):
    fields = asdict(decision)
    label = fields.pop("label")
    record["prediction"] = label if isinstance(label, str) else None
    for key in ("input_tokens", "output_tokens"):
        value = fields[key]
        if value is not None and (type(value) is not int or value < 0):
            fields[key] = None
    for key in ("model_version", "score_type", "provider_request_id"):
        if fields[key] is not None and not isinstance(fields[key], str):
            fields[key] = None
    scores = fields["scores"]
    fields["scores"] = (
        {
            key: value
            for key, value in scores.items()
            if isinstance(key, str) and isinstance(value, (int, float)) and math.isfinite(value)
        }
        if isinstance(scores, dict)
        else {}
    )
    confidence = fields["confidence"]
    if confidence is not None and (
        not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        fields["confidence"] = None
    record.update(fields)


async def measure(adapter, sample, catalog, config, origin, scheduled, phase="measurement"):
    record = base_record(sample, catalog, origin, scheduled, phase)
    dispatched = time.perf_counter()
    record["dispatch_s"] = dispatched - origin
    record["scheduler_lag_ms"] = max(0, (dispatched - scheduled) * 1000)
    try:
        remaining = config.timeout_s - (dispatched - scheduled)
        if remaining <= 0:
            raise TimeoutError
        if config.network_retries:
            record["network_attempts"] = []
            decision = await predict_with_network_retries(
                adapter, sample, catalog, config, scheduled, origin, record["network_attempts"]
            )
        else:
            decision = await asyncio.wait_for(
                adapter.predict(sample.model_input(), catalog), remaining
            )
        attach_decision(record, decision)
        decision.validate(catalog)
        record["status"] = "ok"
    except (TimeoutError, httpx.TimeoutException):
        record.update(status="timeout", error_type="deadline_exceeded")
    except httpx.HTTPStatusError as exc:
        record.update(
            status="http_error",
            http_status=exc.response.status_code,
            error_type="http_status_error",
        )
    except httpx.RequestError:
        record.update(status="network_error", error_type="transport_error")
    except (InvalidOutput, ValueError, TypeError, KeyError, AttributeError) as exc:
        if isinstance(exc, InvalidOutput) and exc.decision is not None:
            attach_decision(record, exc.decision)
        record.update(status="invalid_output", error_type=type(exc).__name__)
    except Exception as exc:
        # Preserve the failure but avoid persisting exception text that may contain secrets.
        record.update(status="adapter_error", error_type=type(exc).__name__)
    completed = time.perf_counter()
    record["completed_s"] = completed - origin
    record["service_latency_ms"] = (completed - dispatched) * 1000
    record["e2e_latency_ms"] = max(0, (completed - scheduled) * 1000)
    return record


async def predict_with_network_retries(
    adapter, sample, catalog, config, scheduled, origin, attempts
):
    """Retry transport errors only, inside the original total request deadline.

    The pending task keeps its concurrency slot throughout retries and backoff.
    HTTP errors and invalid responses propagate immediately; secrets are never logged.
    """
    deadline = scheduled + config.timeout_s
    for index in range(config.network_retries + 1):
        started = time.perf_counter()
        remaining = deadline - started
        if remaining <= 0:
            raise TimeoutError
        attempt = {"attempt": index + 1, "started_s": started - origin}
        attempts.append(attempt)
        try:
            decision = await asyncio.wait_for(
                adapter.predict(sample.model_input(), catalog), remaining
            )
            attempt["status"] = "response_received"
            return decision
        except (httpx.RequestError, TimeoutError) as exc:
            attempt.update(
                status="timeout"
                if isinstance(exc, (TimeoutError, httpx.TimeoutException))
                else "network_error",
                error_type=type(exc).__name__,
                usage_unknown=True,
                completed_s=time.perf_counter() - origin,
            )
            if index == config.network_retries:
                raise
            delay = config.network_retry_backoff_s * (2**index)
            # A 30s total deadline remains 30s, even with retries enabled.
            if time.perf_counter() + delay >= deadline:
                raise
            attempt["retry_backoff_s"] = delay
            await asyncio.sleep(delay)
        except BaseException as exc:
            attempt.update(status="not_retried", error_type=type(exc).__name__)
            raise
        finally:
            attempt.setdefault("completed_s", time.perf_counter() - origin)


async def warmup(adapter, samples, catalog, config, emit):
    origin = time.perf_counter()
    for i in range(config.warmup):
        emit(
            await measure(
                adapter,
                samples[i % len(samples)],
                catalog,
                config,
                origin,
                time.perf_counter(),
                "warmup",
            )
        )


async def quality(
    adapter: BaseAdapter, samples: list[Sample], catalog: Catalog, config: RunConfig, emit
):
    # Sequential by design: quality must not inherit high-load queueing failures.
    origin = time.perf_counter()
    for sample in samples:
        emit(await measure(adapter, sample, catalog, config, origin, time.perf_counter()))
    return time.perf_counter() - origin


async def load(adapter, samples, stages, config, emit):
    """Fixed-rate open loop with bounded tasks and explicit client admission failures.

    stages: [(offset_seconds, Catalog)]. Catalog changes use scheduled arrival time,
    not response completion time. Retries, if configured, retain the same task slot
    and scheduled time, so their overhead remains visible in latency and admission.
    """
    rng = random.Random(config.seed)
    origin = time.perf_counter()
    pending = set()
    stage_index = 0

    async def invoke(sample, catalog, scheduled, phase):
        emit(await measure(adapter, sample, catalog, config, origin, scheduled, phase))

    try:
        count = math.ceil(config.offered_rps * config.duration_s)
        for i in range(count):
            offset = i / config.offered_rps
            if offset >= config.duration_s:
                break
            scheduled = origin + offset
            await asyncio.sleep(max(0, scheduled - time.perf_counter()))
            finished = {task for task in pending if task.done()}
            for task in finished:
                task.result()  # Propagate log-write failures instead of silently losing requests.
            pending -= finished
            while stage_index + 1 < len(stages) and stages[stage_index + 1][0] <= offset:
                stage_index += 1
            catalog = stages[stage_index][1]
            phase = f"stage_{stage_index}" if config.mode == "dynamic" else "measurement"
            sample = samples[rng.randrange(len(samples))]
            if len(pending) >= config.max_concurrency:
                now = time.perf_counter()
                record = base_record(sample, catalog, origin, scheduled, phase)
                record.update(
                    status="client_overload",
                    error_type="concurrency_limit",
                    completed_s=now - origin,
                    scheduler_lag_ms=max(0, (now - scheduled) * 1000),
                )
                emit(record)
            else:
                pending.add(asyncio.create_task(invoke(sample, catalog, scheduled, phase)))
        # Measurement window includes the full configured arrival period, plus drain.
        await asyncio.sleep(max(0, origin + config.duration_s - time.perf_counter()))
        if pending:
            await asyncio.gather(*pending)
    finally:
        for task in pending:
            if not task.done():
                task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    return time.perf_counter() - origin
