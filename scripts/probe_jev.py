"""Validate the documented Jev models and Choice endpoints with one synthetic input."""

import argparse
import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from decisionbench.adapters import INSTRUCTIONS
from decisionbench.artifacts import write_json
from decisionbench.protocol import Catalog, Decision


async def probe(out, network_retries=0):
    token = os.environ["TYPESAFE_API_KEY"]
    catalog = Catalog(
        "synthetic-probe-v1",
        {
            "alarm_set": "Create a new alarm for a specified time.",
            "weather_query": "Ask about weather or a weather forecast.",
        },
    )
    payload = {
        "model": "jev-1.13.0",
        "state": "Set an alarm for seven tomorrow morning.",
        "questions": {
            "intent": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": catalog.labels}
        },
    }
    record = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic": True,
        "evaluation_requests": 0,
        "request": payload,
        "steps": [],
        "network_retries": network_retries,
        "transport_attempts": [],
    }
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=30
    ) as client:
        for method, path, body in (("GET", "/v1/models", None), ("POST", "/v1/systemone", payload)):
            try:
                for attempt_index in range(network_retries + 1):
                    attempt = {"path": path, "attempt": attempt_index + 1}
                    record["transport_attempts"].append(attempt)
                    if method == "POST":
                        record["evaluation_requests"] += 1
                    started = time.perf_counter()
                    try:
                        response = await client.request(
                            method, "https://api.typesafe.ai" + path, json=body
                        )
                        attempt["status"] = response.status_code
                        break
                    except httpx.RequestError as exc:
                        attempt["error_type"] = type(exc).__name__
                        if attempt_index == network_retries:
                            raise
                        await asyncio.sleep(0.5 * 2**attempt_index)
                    finally:
                        attempt["elapsed_ms"] = (time.perf_counter() - started) * 1000
                        write_json(out, record)
                step = {
                    "path": path,
                    "status": response.status_code,
                    "headers": {
                        k: v
                        for k, v in response.headers.items()
                        if k.startswith("x-ratelimit") or k in {"retry-after", "x-request-id"}
                    },
                    "response": response.json(),
                }
                # Never serialize authentication data, even if an error body echoes it.
                import json

                step = json.loads(json.dumps(step).replace(token, "[REDACTED]"))
                record["steps"].append(step)
                write_json(out, record)
                response.raise_for_status()
                if method == "POST":
                    answer = response.json()["answers"]["intent"]
                    decision = Decision(
                        answer["choice"],
                        response.json()["model"],
                        answer["probabilities"],
                        "provider_probability",
                        answer["confidence"],
                    )
                    decision.validate(catalog)
                    record["contract_valid"] = True
                    write_json(out, record)
                print(f"{method} {path}: HTTP {response.status_code}")
            except Exception as exc:
                record["error_type"] = type(exc).__name__
                write_json(out, record)
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--network-retries", type=int, choices=range(4), default=0)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output; no silent retries")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(probe(args.out, args.network_retries))


if __name__ == "__main__":
    main()
