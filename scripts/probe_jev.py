"""Validate the documented Jev models and Choice endpoints with one synthetic input."""

import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from decisionbench.adapters import INSTRUCTIONS
from decisionbench.artifacts import write_json
from decisionbench.protocol import Catalog, Decision


async def probe(out):
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
    }
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=30
    ) as client:
        for method, path, body in (("GET", "/v1/models", None), ("POST", "/v1/systemone", payload)):
            if method == "POST":
                record["evaluation_requests"] += 1
            try:
                response = await client.request(method, "https://api.typesafe.ai" + path, json=body)
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
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output; no silent retries")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(probe(args.out))


if __name__ == "__main__":
    main()
