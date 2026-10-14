from dataclasses import dataclass, field
from math import fsum, isclose, isfinite


@dataclass(frozen=True)
class ModelInput:
    """Ground truth is deliberately unavailable to an adapter."""

    sample_id: str
    text: str


@dataclass(frozen=True)
class Sample:
    sample_id: str
    text: str
    label: str

    def model_input(self) -> ModelInput:
        return ModelInput(self.sample_id, self.text)


@dataclass(frozen=True)
class Catalog:
    version: str
    labels: dict[str, str]
    reject_label: str | None = None


@dataclass
class Decision:
    label: str
    model_version: str
    scores: dict[str, float] = field(default_factory=dict)
    score_type: str | None = None
    confidence: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None

    def validate(self, catalog: Catalog) -> None:
        if not isinstance(self.label, str) or self.label not in catalog.labels:
            raise ValueError("prediction is outside the active catalog")
        if not isinstance(self.model_version, str) or not self.model_version:
            raise ValueError("model_version must be a nonempty string")
        if not isinstance(self.scores, dict):
            raise ValueError("scores must be a mapping")
        for label, score in self.scores.items():
            if label not in catalog.labels or not isinstance(score, (int, float)):
                raise ValueError("invalid score mapping")
            if not isfinite(score):
                raise ValueError("non-finite score")
        if self.score_type in {"provider_probability", "softmax_uncalibrated"} and self.scores:
            if any(not 0 <= value <= 1 for value in self.scores.values()):
                raise ValueError("probabilities outside [0, 1]")
            deviation = abs(fsum(self.scores.values()) - 1)
            # Keep the existing 1% tolerance inclusive at its floating-point boundary.
            if deviation > 0.01 and not isclose(deviation, 0.01, rel_tol=0, abs_tol=1e-12):
                raise ValueError("probabilities do not sum to 1")
        if self.score_type == "provider_probability" and set(self.scores) != set(catalog.labels):
            raise ValueError("provider probabilities must cover the frozen catalog")
        if self.confidence is not None and (
            not isinstance(self.confidence, (int, float))
            or not isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("invalid confidence")
        for count in (self.input_tokens, self.output_tokens):
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError("invalid token count")
