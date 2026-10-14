"""Send one synthetic readiness request through the real Qwen adapter."""

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from decisionbench.adapters import QwenAdapter
from decisionbench.artifacts import write_json
from decisionbench.protocol import Catalog, ModelInput


async def check(base_url, model, out):
    sample = ModelInput("synthetic-readiness-1", "Set an alarm for seven tomorrow morning.")
    catalog = Catalog(
        "synthetic-readiness-v1",
        {
            "alarm_set": "Create a new alarm for a specified time.",
            "weather_query": "Ask about weather or a weather forecast.",
        },
    )
    adapter = QwenAdapter(base_url=base_url, model=model, max_tokens=64)
    record = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic": True,
        "purpose": "Deployment readiness only; excluded from benchmark conclusions.",
        "input": asdict(sample),
        "catalog": asdict(catalog),
    }
    try:
        decision = await asyncio.wait_for(adapter.predict(sample, catalog), timeout=30)
        record.update(status="success", decision=asdict(decision))
    except Exception as exc:
        record.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        await adapter.close()
        write_json(out, record)
    print(f"Synthetic request returned a valid label: {decision.label}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output exists; choose a new readiness log")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(check(args.base_url, args.model, args.out))


if __name__ == "__main__":
    main()
