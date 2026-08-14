import json
from pathlib import Path

from app.main import app


CUSTOMER_FORBIDDEN_SCHEMAS = {
    "InvestigationResponse",
    "EvidenceGraph",
    "AIInvestigatorResponse",
    "ChangeEventResponse",
}


def test_v1_openapi_contract_matches_reviewed_snapshot():
    snapshot = Path(__file__).parents[2] / "docs" / "openapi-v1.json"
    expected = json.loads(snapshot.read_text(encoding="utf-8"))

    assert app.openapi() == expected, (
        "The public v1 API contract changed. Review compatibility and run "
        "`python scripts/update-openapi-contract.py` only for an intentional change."
    )


def test_v1_customer_and_engineer_security_contract_is_frozen():
    schema = app.openapi()
    paths = schema["paths"]
    for path in ("/api/v1/support", "/api/v1/support/trace"):
        success_schema = paths[path]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert success_schema == {
            "$ref": "#/components/schemas/CustomerInvestigationResponse"
        }
        response_model = success_schema["$ref"].rsplit("/", 1)[-1]
        assert response_model not in CUSTOMER_FORBIDDEN_SCHEMAS

    for path in (
        "/api/v1/changes",
        "/api/v1/investigate",
        "/api/v1/investigate/trace",
        "/api/v1/investigate/trace/graph",
        "/api/v1/investigator/trace",
    ):
        assert paths[path]["post"]["security"] == [{"APIKeyHeader": []}]
