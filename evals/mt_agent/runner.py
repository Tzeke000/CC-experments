#!/usr/bin/env python3
"""CLI runner for Making Things multi-step agent evals (MT-4).

Modes:
  mock   — scripted golden tool sequence (no LLM, no Godot). Always runnable.
  live   — OpenAI-compatible tool loop (needs API key). Uses mock tool world
           unless ``MAKING_THINGS_EVAL_LIVE_EDITOR=1`` (documented; not required).

Examples:
  uv run python -m evals.mt_agent.runner --mode mock
  uv run python -m evals.mt_agent.runner --mode mock --case diagnose_broken_script
  uv run python -m evals.mt_agent.runner --mode live --case playtest_live_mutate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evals.mt_agent.cases_loader import EvalCase, get_case, iter_cases
from evals.mt_agent.live_llm import LiveLlmConfig, run_live_llm_case
from evals.mt_agent.mock_session import run_scripted_case
from evals.mt_agent.score import ScoreResult, score_trajectory

REPO = Path(__file__).resolve().parents[2]


def _print(msg: str) -> None:
    print(msg)


async def run_case_mock(case: EvalCase) -> ScoreResult:
    if not case.mock_script:
        return ScoreResult(passed=False, reasons=["case has no mock_script"], called=[])
    calls = await run_scripted_case(case.mock_script)
    return score_trajectory(
        calls,
        required_subsequence=case.required_subsequence or case.expected_tools,
        pass_criteria=case.pass_criteria,
    )


async def run_case_live(case: EvalCase) -> tuple[ScoreResult, str]:
    allowed = list(
        dict.fromkeys(
            [*case.expected_tools, *(step["tool"] for step in case.mock_script)]
        )
    )
    calls, note = await run_live_llm_case(prompt=case.prompt, allowed_tools=allowed)
    if note.startswith("BLOCKED:"):
        return ScoreResult(passed=False, reasons=[note], called=[c.name for c in calls]), note
    score = score_trajectory(
        calls,
        required_subsequence=case.required_subsequence or case.expected_tools,
        pass_criteria=case.pass_criteria,
    )
    if note and not score.passed:
        score.reasons.append(f"model_final: {note[:200]}")
    return score, note


def _result_row(case_id: str, score: ScoreResult, mode: str, extra: str = "") -> dict[str, Any]:
    return {
        "case": case_id,
        "mode": mode,
        "passed": score.passed,
        "called": score.called,
        "reasons": score.reasons,
        "note": extra,
    }


async def _amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--case", action="append", dest="cases", help="Case id (repeatable)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary on stdout",
    )
    args = parser.parse_args(argv)

    if args.cases:
        cases = [get_case(cid) for cid in args.cases]
    else:
        cases = iter_cases()

    rows: list[dict[str, Any]] = []
    failed = 0
    blocked = 0

    for case in cases:
        _print(f"== {case.id}: {case.title} ({args.mode}) ==")
        if args.mode == "mock":
            score = await run_case_mock(case)
            note = ""
        else:
            if LiveLlmConfig.from_env() is None:
                score, note = await run_case_live(case)
            else:
                score, note = await run_case_live(case)
            if note.startswith("BLOCKED:"):
                blocked += 1
                _print(f"BLOCKED  {case.id}: {note}")
            elif score.passed:
                _print(f"PASS  {case.id}")
            else:
                _print(f"FAIL  {case.id}: {score.reasons}")
            rows.append(_result_row(case.id, score, args.mode, note))
            if not score.passed and not note.startswith("BLOCKED:"):
                failed += 1
            continue

        if score.passed:
            _print(f"PASS  {case.id}  tools={score.called}")
        else:
            failed += 1
            _print(f"FAIL  {case.id}: {score.reasons}")
        rows.append(_result_row(case.id, score, args.mode, note if args.mode == "live" else ""))

    summary = {
        "mode": args.mode,
        "passed": sum(1 for r in rows if r["passed"]),
        "failed": failed,
        "blocked": blocked,
        "cases": rows,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print(
            f"\nSummary: {summary['passed']} passed, {failed} failed, {blocked} blocked "
            f"(mode={args.mode})"
        )
        if args.mode == "live" and blocked:
            _print(
                "Live LLM blocked on missing keys — mock mode is the CI/default path. "
                "See docs/making-things/agent-evals.md."
            )

    if failed:
        return 1
    # Blocked live runs are not a hard failure when no keys — exit 2 signals env gap.
    if args.mode == "live" and blocked and summary["passed"] == 0:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    import asyncio

    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    raise SystemExit(main())
