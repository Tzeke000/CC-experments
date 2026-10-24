"""Making Things MT-4 agent eval cases — mock mode always runnable."""

from __future__ import annotations

import asyncio

from evals.mt_agent.cases_loader import iter_cases
from evals.mt_agent.runner import run_case_mock


def test_three_pinned_cases_exist() -> None:
    ids = {c.id for c in iter_cases()}
    assert ids == {
        "diagnose_broken_script",
        "playtest_live_mutate",
        "import_gltf",
    }


def test_mock_runner_passes_all_cases() -> None:
    async def _run() -> None:
        for case in iter_cases():
            score = await run_case_mock(case)
            assert score.passed, f"{case.id} failed: {score.reasons}"

    asyncio.run(_run())


def test_diagnose_case_documents_pass_criteria() -> None:
    case = next(c for c in iter_cases() if c.id == "diagnose_broken_script")
    assert "parse_errors_empty_after_fix" in case.pass_criteria
    assert case.mock_script
    assert case.prompt
