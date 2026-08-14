from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .models import InvestigatorDraft


class ProviderUnavailable(RuntimeError):
    """The configured investigator provider cannot currently be used."""


class ProviderResponseError(RuntimeError):
    """The provider failed or returned an invalid structured response."""


@dataclass(slots=True)
class ProviderRequest:
    system_prompt: str
    user_payload: dict[str, Any]


@dataclass(slots=True)
class ProviderResult:
    provider: str
    model: str | None
    draft: InvestigatorDraft


class InvestigatorProvider(Protocol):
    async def generate(self, request: ProviderRequest) -> ProviderResult:
        ...


class DisabledProvider:
    async def generate(self, request: ProviderRequest) -> ProviderResult:
        _ = request
        raise ProviderUnavailable("AI Investigator is disabled")


class OpenAIResponsesProvider:
    """Minimal OpenAI Responses API adapter using strict structured outputs."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderUnavailable("PRODMIND_LLM_API_KEY is required")
        if not model:
            raise ProviderUnavailable("PRODMIND_LLM_MODEL is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        payload = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        request.user_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "prodmind_investigator",
                    "strict": True,
                    "schema": _investigator_schema(),
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderResponseError("OpenAI Responses API request failed") from exc

        try:
            response_payload = response.json()
            output_text = _extract_output_text(response_payload)
            draft = InvestigatorDraft.model_validate_json(output_text)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderResponseError("OpenAI returned an invalid investigator response") from exc

        return ProviderResult(provider="openai", model=self.model, draft=draft)


def configured_investigator_provider() -> InvestigatorProvider:
    provider = os.getenv("PRODMIND_LLM_PROVIDER", "disabled").strip().lower()
    if provider in {"", "disabled", "none"}:
        return DisabledProvider()
    if provider == "openai":
        timeout = _float_env("PRODMIND_LLM_TIMEOUT_SECONDS", 30.0)
        return OpenAIResponsesProvider(
            api_key=os.getenv("PRODMIND_LLM_API_KEY", ""),
            model=os.getenv("PRODMIND_LLM_MODEL", ""),
            base_url=os.getenv("PRODMIND_LLM_BASE_URL", "https://api.openai.com/v1"),
            timeout_seconds=timeout,
        )
    raise ProviderUnavailable(f"Unsupported AI Investigator provider: {provider}")


def _extract_output_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
            if content.get("type") == "refusal":
                raise ValueError("provider refused the request")
    raise ValueError("response has no output_text")


def _investigator_schema() -> dict[str, Any]:
    step_enum = [
        "inspect_trace",
        "inspect_logs",
        "inspect_metrics",
        "inspect_changes",
        "inspect_history",
        "ask_for_context",
    ]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["summary", "evidence_ids"],
                },
            },
            "missing_evidence": {
                "type": "array",
                "items": {"type": "string"},
            },
            "next_steps": {
                "type": "array",
                "items": {"type": "string", "enum": step_enum},
            },
        },
        "required": ["answer", "claims", "missing_evidence", "next_steps"],
    }


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, 1.0), 120.0)
