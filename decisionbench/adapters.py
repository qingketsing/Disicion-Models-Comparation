import asyncio
import json
import os
import re
from abc import ABC, abstractmethod

import httpx

from decisionbench.protocol import Catalog, Decision, ModelInput

INSTRUCTIONS = "Select the single intent that best matches the user's request from the catalog."


def qwen_messages(sample: ModelInput, catalog: Catalog):
    return [
        {
            "role": "system",
            "content": INSTRUCTIONS
            + '\nReturn only JSON: {"label":"<intent>"}.\n'
            + "Catalog:\n"
            + json.dumps(catalog.labels, ensure_ascii=False),
        },
        {"role": "user", "content": sample.text},
    ]


class InvalidOutput(ValueError):
    def __init__(self, message: str, decision: Decision | None = None):
        super().__init__(message)
        self.decision = decision


class BaseAdapter(ABC):
    @abstractmethod
    async def predict(self, sample: ModelInput, catalog: Catalog) -> Decision:
        raise NotImplementedError

    async def close(self):
        pass


class MockAdapter(BaseAdapter):
    """Synthetic rule model; never reads ground truth."""

    def __init__(self, rules=None, delay_ms=5, **kwargs):
        self.rules = rules or {
            "cancel": "alarm_cancel",
            "weather": "weather_query",
            "alarm": "alarm_set",
        }
        self.delay_ms = delay_ms

    async def predict(self, sample, catalog):
        await asyncio.sleep(self.delay_ms / 1000)
        label = next(
            (value for key, value in self.rules.items() if key in sample.text.lower()),
            catalog.reject_label or next(iter(catalog.labels)),
        )
        return Decision(label, "mock-rules-v1")


class HTTPAdapter(BaseAdapter):
    def __init__(self, base_url, model="", api_key_env=None, max_connections=64, **kwargs):
        token = os.environ.get(api_key_env, "") if api_key_env else ""
        if api_key_env and not token:
            raise ValueError(f"missing environment variable: {api_key_env}")
        self.base_url = os.path.expandvars(base_url).rstrip("/")
        if "$" in self.base_url:
            raise ValueError("unresolved environment variable in base_url")
        self.model = model
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=None,  # Harness owns the total end-to-end deadline; no hidden retries.
            limits=httpx.Limits(
                max_connections=max_connections, max_keepalive_connections=max_connections
            ),
            follow_redirects=False,
        )

    async def post(self, path, payload):
        response = await self.client.post(self.base_url + path, json=payload)
        response.raise_for_status()
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except ValueError as exc:
            raise InvalidOutput("response is not a JSON object") from exc
        return data, response.headers.get("x-request-id")

    async def close(self):
        await self.client.aclose()


class JevAdapter(HTTPAdapter):
    async def predict(self, sample, catalog):
        if len(catalog.labels) > 255:
            raise ValueError("Jev Choice supports at most 255 options")
        data, request_id = await self.post(
            "/v1/systemone",
            {
                "model": self.model,
                "state": sample.text,
                "questions": {
                    "intent": {
                        "type": "choice",
                        "instructions": INSTRUCTIONS,
                        "criteria": catalog.labels,
                    }
                },
            },
        )
        usage = data.get("usage") or {}
        decision = Decision(
            "",
            data.get("model", self.model),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            provider_request_id=request_id,
        )
        try:
            answer = data["answers"]["intent"]
            decision.label = answer["choice"]
            decision.scores = answer["probabilities"]
            decision.confidence = answer["confidence"]
            decision.score_type = "provider_probability"
            decision.validate(catalog)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise InvalidOutput("malformed Jev Choice answer", decision) from exc
        return decision


class QwenAdapter(HTTPAdapter):
    def __init__(self, max_tokens=64, constrain_labels=False, **kwargs):
        super().__init__(**kwargs)
        self.max_tokens = max_tokens
        self.constrain_labels = constrain_labels

    async def predict(self, sample, catalog):
        payload = {
            "model": self.model,
            "messages": qwen_messages(sample, catalog),
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self.constrain_labels:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "intent_decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"label": {"type": "string", "enum": list(catalog.labels)}},
                        "required": ["label"],
                        "additionalProperties": False,
                    },
                },
            }
        data, request_id = await self.post("/v1/chat/completions", payload)
        usage = data.get("usage") or {}
        decision = Decision(
            "",
            data.get("model", self.model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            provider_request_id=request_id or data.get("id"),
        )
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("generation did not finish normally")
            content = choice["message"]["content"].strip()
            # Accept a single JSON code fence, never substring-match a category from prose.
            match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL)
            parsed = json.loads(match.group(1) if match else content)
            decision.label = parsed["label"]
            decision.validate(catalog)
        except (KeyError, ValueError, TypeError, IndexError, AttributeError) as exc:
            raise InvalidOutput("invalid or truncated Qwen label JSON", decision) from exc
        return decision


class ClassifierAdapter(HTTPAdapter):
    async def predict(self, sample, catalog):
        data, request_id = await self.post(
            "/predict",
            {
                "sample_id": sample.sample_id,
                "text": sample.text,
                "catalog": {"version": catalog.version, "labels": catalog.labels},
            },
        )
        try:
            return Decision(
                data["label"],
                data["model_version"],
                scores=data.get("scores", {}),
                score_type=data.get("score_type"),
                confidence=data.get("confidence"),
                provider_request_id=request_id,
            )
        except (KeyError, TypeError) as exc:
            raise InvalidOutput("malformed classifier response") from exc


def create_adapter(config: dict, max_concurrency: int) -> BaseAdapter:
    options = dict(config)
    kind = options.pop("kind")
    constructors = {
        "mock": MockAdapter,
        "jev": JevAdapter,
        "qwen": QwenAdapter,
        "bert": ClassifierAdapter,
        "classic": ClassifierAdapter,
    }
    if kind not in constructors:
        raise ValueError(f"unknown adapter kind: {kind}")
    if kind != "mock":
        options["max_connections"] = max_concurrency
    return constructors[kind](**options)
