from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class LogFacts:
    lines: list[str]
    exception_type: str | None = None
    exception_message: str | None = None


class LokiConnector:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def query_trace_logs(
        self,
        trace_id: str,
        service_name: str = "demo-user-service",
        lookback_seconds: int = 300,
        limit: int = 100,
    ) -> LogFacts:
        now_ns = time.time_ns()
        start_ns = now_ns - lookback_seconds * 1_000_000_000
        query = f'{{service_name="{service_name}"}} |= "{trace_id}"'
        params = {
            "query": query,
            "start": str(start_ns),
            "end": str(now_ns),
            "limit": str(limit),
            "direction": "backward",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/loki/api/v1/query_range", params=params)
            response.raise_for_status()
            payload = response.json()

        lines: list[str] = []
        for stream in payload.get("data", {}).get("result", []):
            for _, line in stream.get("values", []):
                if line:
                    lines.append(line)

        exception_type, exception_message = _extract_exception(lines)
        return LogFacts(
            lines=lines,
            exception_type=exception_type,
            exception_message=exception_message,
        )


def _extract_exception(lines: list[str]) -> tuple[str | None, str | None]:
    for line in lines:
        lower = line.lower()
        if "duplicatekeyexception" in lower or "duplicate key" in lower or "unique constraint" in lower:
            return "DuplicateKeyException", line[-2000:]
    return None, None
