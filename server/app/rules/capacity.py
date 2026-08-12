from __future__ import annotations

from ..models import Evidence, InvestigationRequest, RootCause
from .base import RuleMatch


class DatabasePoolExhaustedRule:
    name = "database_pool_exhausted"

    def evaluate(self, request: InvestigationRequest) -> RuleMatch | None:
        exception_type = (request.exception_type or "").lower()
        message = (request.exception_message or "").lower()

        acquisition_timeout = (
            "cannotgetjdbcconnectionexception" in exception_type
            or "sqltransientconnectionexception" in exception_type
            or "connection is not available" in message
            or ("hikaripool" in message and "timed out" in message)
        )
        if not acquisition_timeout:
            return None

        metrics = {sample.name: sample.value for sample in request.metric_samples}
        active = metrics.get("db_pool_active")
        maximum = metrics.get("db_pool_max")
        pending = metrics.get("db_pool_pending", 0.0)

        # A connection timeout alone can have several causes. Require recent
        # project/service-scoped pool saturation before assigning this RCA.
        if active is None or maximum is None or maximum <= 0 or active < maximum:
            return None

        confidence = 0.99 if pending >= 1 else 0.97
        return RuleMatch(
            root_cause=RootCause(
                category="database_pool_exhausted",
                summary="The application database connection pool was exhausted.",
                confidence=confidence,
            ),
            evidence=[
                Evidence(
                    type="database",
                    summary="Database connection acquisition timed out while the application pool was saturated.",
                    source="rca-rule:database-pool-exhausted",
                ),
                Evidence(
                    type="metric",
                    summary=(
                        "Recent database pool pressure confirmed saturation: "
                        f"active peak {active:g}/{maximum:g} connections; "
                        f"pending peak {pending:g}."
                    ),
                    source="rca-rule:database-pool-exhausted",
                ),
            ],
            customer_answer=(
                "The operation could not get the internal capacity it needed in time. "
                "Please retry shortly."
            ),
            engineer_answer=(
                "The request timed out acquiring a database connection, and recent project-scoped "
                f"metrics show the pool saturated at {active:g}/{maximum:g} active connections "
                f"with a pending peak of {pending:g}."
            ),
            recommended_actions=[
                "Identify requests or queries holding database connections for unusually long periods.",
                "Check for connection leaks and transactions that remain open across slow work.",
                "Review pool sizing against database capacity before increasing the maximum connection count.",
                "Inspect slow-query and database saturation metrics around the incident window.",
            ],
        )
