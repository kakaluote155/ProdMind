import json
from pathlib import Path

from app.main import app


def test_v1_openapi_contract_matches_reviewed_snapshot():
    snapshot = Path(__file__).parents[2] / "docs" / "openapi-v1.json"
    expected = json.loads(snapshot.read_text(encoding="utf-8"))

    assert app.openapi() == expected, (
        "The public v1 API contract changed. Review compatibility and run "
        "`python scripts/update-openapi-contract.py` only for an intentional change."
    )
