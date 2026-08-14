from __future__ import annotations

import os
import json
import ssl
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import ConfigurationError, boolean_env, positive_float_env, positive_int_env


@dataclass(frozen=True, slots=True)
class ConnectorHttpOptions:
    timeout_seconds: float = 5.0
    max_response_bytes: int = 5_000_000
    bearer_token: str | None = None
    verify: bool | ssl.SSLContext = True

    def client(self) -> httpx.AsyncClient:
        headers = {"Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=headers,
            verify=self.verify,
            follow_redirects=False,
        )

    async def get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Fetch JSON while enforcing the response limit during streaming."""

        async with client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            self._validate_content_length(response)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > self.max_response_bytes:
                    raise httpx.DecodingError("connector response exceeds configured limit")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise httpx.DecodingError("connector returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise httpx.DecodingError("connector JSON response must be an object")
        return payload

    def _validate_content_length(self, response: httpx.Response) -> None:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_response_bytes:
                    raise httpx.DecodingError("connector response exceeds configured limit")
            except ValueError:
                pass


def configured_http_options(connector: str) -> ConnectorHttpOptions:
    connector = connector.upper()
    timeout = positive_float_env("PRODMIND_CONNECTOR_TIMEOUT_SECONDS", 5.0)
    max_bytes = positive_int_env(
        "PRODMIND_CONNECTOR_MAX_RESPONSE_BYTES",
        5_000_000,
        minimum=1024,
    )
    token = os.getenv(f"PRODMIND_{connector}_BEARER_TOKEN", "").strip() or None
    verify_enabled = boolean_env("PRODMIND_OBSERVABILITY_TLS_VERIFY", True)
    ca_file = os.getenv("PRODMIND_OBSERVABILITY_CA_FILE", "").strip()
    if ca_file and not verify_enabled:
        raise ConfigurationError(
            "PRODMIND_OBSERVABILITY_CA_FILE cannot be used when TLS verification is disabled"
        )
    verify: bool | ssl.SSLContext
    if ca_file:
        try:
            verify = ssl.create_default_context(cafile=ca_file)
        except (OSError, ssl.SSLError) as exc:
            raise ConfigurationError("observability CA file cannot be loaded") from exc
    else:
        verify = verify_enabled
    return ConnectorHttpOptions(
        timeout_seconds=timeout,
        max_response_bytes=max_bytes,
        bearer_token=token,
        verify=verify,
    )
