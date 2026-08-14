from __future__ import annotations

from typing import Any, Awaitable, Callable

from .telemetry import mark_current_span, validate_project_id

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[dict[str, Any], ASGIReceive, ASGISend], Awaitable[None]]


class ProdMindASGIMiddleware:
    """Tag the current HTTP server span with configured ProdMind project scope."""

    def __init__(self, app: ASGIApp, *, project_id: str) -> None:
        self.app = app
        self.project_id = validate_project_id(project_id)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope.get("type") == "http":
            mark_current_span(self.project_id)
        await self.app(scope, receive, send)
