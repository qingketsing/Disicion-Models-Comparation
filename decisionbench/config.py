import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RunConfig:
    name: str
    mode: str
    dataset: str
    catalog: str
    adapter: dict
    output_dir: str = "results"
    seed: int = 42
    timeout_s: float = 30
    slo_ms: float = 500
    warmup: int = 0
    offered_rps: float = 1
    duration_s: float = 10
    max_concurrency: int = 4
    min_success_rate: float = 0.99
    max_scheduler_lag_ms: float = 20
    cost: dict = field(default_factory=dict)
    environment: dict = field(default_factory=dict)
    stages: list[dict] = field(default_factory=list)
    network_retries: int = 0
    network_retry_backoff_s: float = 0.5

    def __post_init__(self):
        if self.mode not in {"quality", "load", "dynamic"}:
            raise ValueError(
                "mode must be quality, load or dynamic; cost is an offline CLI command"
            )
        if not self.name or not isinstance(self.adapter, dict):
            raise ValueError("name and adapter mapping are required")
        for key in ("timeout_s", "slo_ms", "offered_rps", "duration_s", "max_scheduler_lag_ms"):
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        for key, lower in (("warmup", 0), ("max_concurrency", 1)):
            if type(getattr(self, key)) is not int or getattr(self, key) < lower:
                raise ValueError(f"invalid {key}")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if type(self.network_retries) is not int or not 0 <= self.network_retries <= 3:
            raise ValueError("network_retries must be an integer between 0 and 3")
        if (
            not isinstance(self.network_retry_backoff_s, (int, float))
            or not math.isfinite(self.network_retry_backoff_s)
            or self.network_retry_backoff_s < 0
        ):
            raise ValueError("network_retry_backoff_s must be finite and nonnegative")
        if not 0 <= self.min_success_rate <= 1:
            raise ValueError("min_success_rate must be between 0 and 1")
        if self.offered_rps * self.duration_s > 1_000_000:
            raise ValueError("v0.1 supports at most 1M offered requests per run")
        if self.stages and self.mode != "dynamic":
            raise ValueError("stages only apply to dynamic runs")
        if self.mode == "dynamic":
            offsets = [s.get("at_s") for s in self.stages]
            if (
                not offsets
                or offsets[0] != 0
                or any(
                    not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    or not 0 <= v < self.duration_s
                    for v in offsets
                )
                or offsets != sorted(set(offsets))
            ):
                raise ValueError("dynamic stages must start at 0 and increase within duration_s")
            if any(not isinstance(s.get("catalog"), str) for s in self.stages):
                raise ValueError("each dynamic stage requires a catalog")


def load_config(path: Path) -> RunConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a YAML mapping")
    return RunConfig(**data)


def resolve_path(root: Path, path: str) -> Path:
    return (root / path).resolve()
