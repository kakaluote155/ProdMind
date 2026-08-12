from __future__ import annotations

from ..models import Evidence, InvestigationRequest, RootCause
from .base import RuleMatch


class SlowDatabaseQueryRule:
    name = "slow_database_query"

    def evaluate(self, request: InvestigationRequest) -> RuleMatch | None:
        # Performance RCA is intentionally separate from server-error RCA. A
        # failed request may contain a long DB span, but that does not make
        # latency the primary root cause.
        if request.http_status is not None and request.http_status >= 500:
            return None

        total_ms = request.trace_duration_ms
        if total_ms is None or total_ms < 1500:
            return None

        database_spans = [
            sample
            for sample in request.span_samples
            if sample.category == "database"
        ]
        if not database_spans:
            return None

        dominant = max(database_spans, key=lambda sample: sample.duration_ms)
        if dominant.duration_ms < 1000:
            return None

        ratio = dominant.duration_ms / total_ms if total_ms > 0 else 0.0
        if ratio < 0.70:
            return None

        confidence = 0.98 if ratio >= 0.85 else 0.94
        ratio_percent = ratio * 100

        return RuleMatch(
            root_cause=RootCause(
                category="slow_database_query",
                summary="A database operation dominated the request latency.",
                confidence=confidence,
            ),
            evidence=[
                Evidence(
                    type="database",
                    summary=(
                        f"Dominant database span {dominant.name} took "
                        f"{dominant.duration_ms:.0f} ms, about {ratio_percent:.0f}% "
                        f"of the {total_ms:.0f} ms trace."
                    ),
                    source="rca-rule:slow-database-query",
                ),
                Evidence(
                    type="trace",
                    summary=(
                        f"Successful operation trace duration: {total_ms:.0f} ms; "
                        f"database contribution: {ratio_percent:.0f}%."
                    ),
                    source="rca-rule:slow-database-query",
                ),
            ],
            customer_answer=(
                "The operation completed, but most of the delay occurred while processing data "
                "in the backend. The engineering team can investigate and optimize that slow path."
            ),
            engineer_answer=(
                f"The request completed in {total_ms:.0f} ms. The dominant database operation "
                f"({dominant.name}) consumed {dominant.duration_ms:.0f} ms "
                f"({ratio_percent:.0f}% of the trace), making it the primary latency bottleneck."
            ),
            recommended_actions=[
                "Inspect the slow database operation's execution plan and index usage.",
                "Check for lock waits, large scans and unexpected result-set growth.",
                "Compare the operation latency with recent baseline traces before changing capacity.",
                "Optimize the query or data-access pattern, then verify with a new trace.",
            ],
        )
