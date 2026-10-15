import math
from collections import Counter


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * p / 100
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def distribution(values):
    return {f"p{p}_ms": percentile(values, p) for p in (50, 95, 99)}


def quality_metrics(records, labels):
    total = len(records)
    successful = [r for r in records if r["status"] == "ok"]
    correct = sum(r["prediction"] == r["expected_label"] for r in successful)
    support = Counter(r["expected_label"] for r in records)
    predicted = Counter(r["prediction"] for r in successful)
    true_positives = Counter(
        r["prediction"] for r in successful if r["prediction"] == r["expected_label"]
    )
    per_class = {}
    confusion = Counter(
        (r["expected_label"], r["prediction"] if r["status"] == "ok" else "__failure__")
        for r in records
    )
    for label in sorted(labels):
        tp = true_positives[label]
        fp = predicted[label] - tp
        fn = support[label] - tp  # Errors and rejections remain false negatives.
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0
        per_class[label] = {
            "support": support[label],
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    supported = [v["f1"] for v in per_class.values() if v["support"]]
    return {
        "accuracy": correct / total if total else None,
        "accuracy_successful_only": correct / len(successful) if successful else None,
        "macro_f1": sum(v["f1"] for v in per_class.values()) / len(per_class)
        if per_class
        else None,
        "macro_f1_supported_classes": sum(supported) / len(supported) if supported else None,
        "macro_f1_scope": "all frozen catalog labels; zero division = 0",
        "reject_rate": sum(
            r["prediction"] == r.get("reject_label") and r.get("reject_label") is not None
            for r in successful
        )
        / total
        if total
        else None,
        "per_class": per_class,
        "confusion": [
            {"expected": a, "predicted": b, "count": n} for (a, b), n in sorted(confusion.items())
        ],
    }


def summarize(records, config, elapsed_s, labels):
    n = len(records)
    ok = [r for r in records if r["status"] == "ok"]
    valid = [r for r in ok if r["e2e_latency_ms"] <= config.slo_ms]
    correct_valid = [r for r in valid if r["prediction"] == r["expected_label"]]
    attempted = [r for r in records if r["dispatch_s"] is not None]
    lags = [r["scheduler_lag_ms"] for r in records if r["scheduler_lag_ms"] is not None]
    all_latency = distribution([r["e2e_latency_ms"] for r in attempted])
    rate = len(ok) / n if n else 0
    max_lag = max(lags, default=0)
    summary = {
        "mode": config.mode,
        "offered_requests": n,
        "attempted_requests": len(attempted),
        "successful_requests": len(ok),
        "status_counts": dict(Counter(r["status"] for r in records)),
        "elapsed_s_including_drain": elapsed_s,
        "slo_ms": config.slo_ms,
        "success_rate": rate,
        "completed_throughput_qps": len(ok) / elapsed_s if elapsed_s else 0,
        "goodput_qps": len(valid) / elapsed_s if elapsed_s else 0,
        "correct_goodput_qps": len(correct_valid) / elapsed_s if elapsed_s else 0,
        "slo_valid_requests": len(valid),
        "latency_attempted": all_latency,
        "latency_successful": distribution([r["e2e_latency_ms"] for r in ok]),
        "scheduler_lag": {**distribution(lags), "max_ms": max_lag},
        "client_measurement_valid": max_lag <= config.max_scheduler_lag_ms,
        "slo_capacity_candidate": bool(
            config.mode == "load"
            and n
            and rate >= config.min_success_rate
            and all_latency["p95_ms"] is not None
            and all_latency["p95_ms"] <= config.slo_ms
            and max_lag <= config.max_scheduler_lag_ms
        ),
        "quality": quality_metrics(records, labels),
    }
    if config.mode in {"load", "dynamic"}:
        summary.update(
            offered_rps=config.offered_rps,
            arrival_window_s=config.duration_s,
            observed_offered_rps=n / config.duration_s,
        )
        summary["quality_note"] = (
            "Quality under load; use a separate quality run for semantic baseline."
        )
    if any("network_attempts" in r for r in records):
        attempts = [a for r in records for a in r.get("network_attempts", [])]
        summary["network_retry"] = {
            "max_additional_retries": config.network_retries,
            "total_request_deadline_s": config.timeout_s,
            "adapter_attempts": len(attempts),
            "additional_attempts": sum(
                max(0, len(r.get("network_attempts", [])) - 1) for r in records
            ),
            "transport_failures": sum(
                a["status"] in {"network_error", "timeout"} for a in attempts
            ),
            "recovered_requests": sum(
                r["status"] == "ok" and len(r.get("network_attempts", [])) > 1 for r in records
            ),
            "latency_scope": "original scheduled arrival through retries and backoff to completion",
        }
    summary["cost"] = request_cost(records, elapsed_s, config.cost, config.slo_ms)
    return summary


def request_cost(records, elapsed_s, pricing, slo_ms):
    if not pricing:
        return {"configured": False}
    mode = pricing.get("billing", "instance")
    currency = pricing.get("currency")
    if not currency:
        raise ValueError("cost.currency is required")
    n = len(records)
    successful = sum(r["status"] == "ok" for r in records)
    valid = sum(r["status"] == "ok" and r["e2e_latency_ms"] <= slo_ms for r in records)
    price_keys = {
        "instance": ["instance_price_per_hour"],
        "api": ["input_price_per_million", "output_price_per_million"],
    }
    if mode not in price_keys:
        raise ValueError("cost.billing must be instance or api")
    for key in price_keys[mode]:
        value = pricing.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"cost.{key} must be a finite nonnegative number")
    complete = True
    if mode == "instance":
        total = elapsed_s * pricing["instance_price_per_hour"] / 3600
    else:
        complete = all(
            r.get("input_tokens") is not None
            and r.get("output_tokens") is not None
            and not any(a.get("usage_unknown") for a in r.get("network_attempts", []))
            for r in records
            if r["status"] != "client_overload"
        )
        total = (
            sum(
                (r.get("input_tokens") or 0) * pricing["input_price_per_million"]
                + (r.get("output_tokens") or 0) * pricing["output_price_per_million"]
                for r in records
            )
            / 1_000_000
        )
    return {
        "configured": True,
        "billing": mode,
        "currency": currency,
        "pricing": pricing,
        "total_measured_cost": total,
        "usage_complete": complete,
        "cost_per_million_successful": total * 1_000_000 / successful if successful else None,
        "cost_per_million_slo_valid": total * 1_000_000 / valid if valid else None,
        "offered_requests": n,
        "scope": "measurement and drain; warmup, training and idle time excluded",
        "estimate_note": "API cost is a lower bound when usage_complete is false",
    }


def monthly_tco(
    monthly_requests,
    peak_rps,
    max_slo_qps,
    instance_price_per_hour,
    hours=730,
    utilization=0.7,
    training_cost=0,
    maintenance_cost=0,
):
    for value in (
        monthly_requests,
        peak_rps,
        instance_price_per_hour,
        hours,
        training_cost,
        maintenance_cost,
    ):
        if not math.isfinite(value) or value < 0:
            raise ValueError("TCO inputs must be finite and nonnegative")
    if hours == 0 or not math.isfinite(max_slo_qps) or max_slo_qps <= 0 or not 0 < utilization <= 1:
        raise ValueError("hours/capacity must be positive; utilization must be in (0, 1]")
    average = monthly_requests / (hours * 3600)
    if peak_rps < average:
        raise ValueError("peak_rps cannot be smaller than average monthly RPS")
    replicas = math.ceil(max(peak_rps, average) / (max_slo_qps * utilization))
    total = replicas * hours * instance_price_per_hour + training_cost + maintenance_cost
    return {
        "replicas": replicas,
        "monthly_tco": total,
        "average_rps": average,
        "capacity_utilization_target": utilization,
        "cost_per_million": total * 1_000_000 / monthly_requests if monthly_requests else None,
        "assumptions": "Always-on replicas, no autoscaling, capacity independently validated.",
    }
