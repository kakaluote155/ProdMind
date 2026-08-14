from pathlib import Path

import pytest

from app.ai_eval import run_suite


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_all_ai_quality_gate_cases_pass():
    cases = Path(__file__).parents[1] / "app" / "ai_eval_cases.json"
    results = await run_suite(cases)

    failures = [f"{result.name}: {result.detail}" for result in results if not result.passed]
    assert not failures, "\n".join(failures)
    assert len(results) >= 8
