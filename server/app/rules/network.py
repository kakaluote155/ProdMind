from __future__ import annotations

from ..models import Evidence, InvestigationRequest, RootCause
from .base import RuleMatch


class DownstreamUnavailableRule:
    name = "downstream_unavailable"

    def evaluate(self, request: InvestigationRequest) -> RuleMatch | None:
        exception_type = (request.exception_type or "").lower()
        message = (request.exception_message or "").lower()

        exception_signature = any(
            signature in exception_type
            for signature in (
                "connectexception",
                "resourceaccessexception",
                "httpconnecttimeoutexception",
            )
        )
        message_signature = any(
            signature in message
            for signature in (
                "connection refused",
                "failed to connect",
                "connect timed out",
                "connection timed out",
            )
        )
        if not (exception_signature or message_signature):
            return None

        return RuleMatch(
            root_cause=RootCause(
                category="downstream_unavailable",
                summary="A required downstream dependency could not be reached.",
                confidence=0.96,
            ),
            evidence=[
                Evidence(
                    type="dependency",
                    summary="Downstream dependency connectivity failure detected from exception evidence.",
                    source="rca-rule:downstream-unavailable",
                )
            ],
            customer_answer=(
                "The operation could not be completed because a required service is temporarily unavailable. "
                "Please try again shortly."
            ),
            engineer_answer=(
                "A downstream connectivity failure was detected. Inspect the failing client span, "
                "service health, DNS/network reachability, and timeout/retry configuration."
            ),
            recommended_actions=[
                "Identify the failing downstream client span and target service.",
                "Verify that the dependency is running and reachable from the caller.",
                "Check DNS, network policy, load balancer, timeout and retry configuration.",
            ],
        )
