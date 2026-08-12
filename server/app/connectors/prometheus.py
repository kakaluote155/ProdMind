from __future__ import annotations

import math
from typing import Any

import httpx

from ..models import MetricSample


class PrometheusConnector:
    """Small Prometheus HTTP API adapter that returns normalized metric facts."""

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def query_value(self, expression: str) -> float | None:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await self._query_value(client, expression)

    async def query_hikari_pool_snapshot(
        self,
        *,
        project_id: str,
        service_name: str,
        lookback: str = "30s",
    ) -> list[MetricSample]:
        """Return recent peak Hikari pool pressure for one project/service.

        We intentionally query a short lookback window rather than only the
        current instant. Connection acquisition failures are short-lived, and the
        request may already have timed out by the time ProdMind investigates it.
        """

        selector = (
            f'{{application="{_escape_label(service_name)}",'
            f'prodmind_project="{_escape_label(project_id)}"}}'
        )
        queries = {
            "db_pool_active": f"max(max_over_time(hikaricp_connections_active{selector}[{lookback}]))",
            "db_pool_max": f"max(max_over_time(hikaricp_connections_max{selector}[{lookback}]))",
            "db_pool_pending": f"max(max_over_time(hikaricp_connections_pending{selector}[{lookback}]))",
        }

        samples: list[MetricSample] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for name, expression in queries.items():
                value = await self._query_value(client, expression)
                if value is None:
                    continue
                samples.append(
                    MetricSample(
                        name=name,
                        value=value,
                        unit="connections",
                        source="prometheus",
                        labels={
                            "project_id": project_id,
                            "service_name": service_name,
                            "lookback": lookback,
                        },
                    )
                )
        return samples

    async def _query_value(
        self,
        client: httpx.AsyncClient,
        expression: str,
    ) -> float | None:
        response = await client.get(
            f"{self.base_url}/api/v1/query",
            params={"query": expression},
        )
        response.raise_for_status()
        return _extract_query_value(response.json())


def _extract_query_value(payload: dict[str, Any]) -> float | None:
    if payload.get("status") != "success":
        return None

    data = payload.get("data") or {}
    result_type = data.get("resultType")
    result = data.get("result")

    raw_value: Any = None
    if result_type == "vector" and isinstance(result, list) and result:
        raw_value = (result[0].get("value") or [None, None])[1]
    elif result_type == "scalar" and isinstance(result, list) and len(result) >= 2:
        raw_value = result[1]

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
