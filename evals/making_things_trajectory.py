#!/usr/bin/env python3
"""Minimal Making Things agent-trajectory harness (non-LLM).

Upstream LLM agent evals live in **godot-agents** (``godot_agent_harness``).
This repo keeps a scripted checklist that exercises the same Phase 4 diagnose
path an agent would follow — no model required — so CI/cloud can stay green.

Usage:
    uv run python -m evals.making_things_trajectory
    uv run python -m evals.making_things_trajectory --skip-godot   # structural only

Exit 0 = all checks passed. Exit 1 = failure. Exit 2 = environmental blocker
(missing Godot) with a concrete next step printed to stderr.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _ok(name: str) -> None:
    print(f"PASS  {name}")


def _fail(name: str, detail: str) -> None:
    print(f"FAIL  {name}: {detail}", file=sys.stderr)


def check_structural() -> list[str]:
    """Files / skills / prompts an agent trajectory depends on."""
    failures: list[str] = []
    required = [
        REPO / "docs" / "making-things" / "diagnose-broken-script.md",
        REPO / "scripts" / "diagnose_fixture_smoke.sh",
        REPO / "scripts" / "csharp_fixture_smoke.sh",
        REPO / ".agents" / "skills" / "making-things-godot-playtest-debug" / "SKILL.md",
        REPO / ".agents" / "skills" / "making-things-godot-observability" / "SKILL.md",
        REPO / "fixtures" / "godot_project" / "project.godot",
        REPO / "fixtures" / "godot_csharp_project" / "MakingThingsCsharpFixture.csproj",
    ]
    for path in required:
        if path.is_file():
            _ok(f"exists:{path.relative_to(REPO)}")
        else:
            failures.append(f"missing {path.relative_to(REPO)}")
            _fail(f"exists:{path.relative_to(REPO)}", "not found")

    prompts = (REPO / "mcp_server" / "prompts" / "prompts.py").read_text(encoding="utf-8")
    for name in ("playtest_loop", "fix_import"):
        if f'"{name}"' in prompts or f"'{name}'" in prompts or f"name=\"{name}\"" in prompts:
            _ok(f"prompt:{name}")
        else:
            # prompts register via decorators — also accept bare identifier
            if name in prompts:
                _ok(f"prompt:{name}")
            else:
                failures.append(f"prompt {name} missing")
                _fail(f"prompt:{name}", "not found in prompts.py")

    checklist = (REPO / "docs" / "making-things" / "diagnose-broken-script.md").read_text(
        encoding="utf-8"
    )
    for needle in (
        "godot_scripts_get_parse_errors",
        "godot_get_open_errors",
        "Pass criteria",
    ):
        if needle in checklist:
            _ok(f"checklist:{needle}")
        else:
            failures.append(f"checklist missing {needle}")
            _fail(f"checklist:{needle}", "not in diagnose-broken-script.md")
    return failures


def check_diagnose_smoke() -> list[str]:
    godot = os.environ.get("GODOT_MCP_GODOT_BIN") or os.environ.get("GODOT_BIN")
    if not godot:
        home = Path.home() / "godot" / "Godot_v4.7.2-stable_linux.x86_64"
        if home.is_file():
            godot = str(home)
    if not godot or not Path(godot).is_file():
        print(
            "BLOCKER: Godot binary not found. Next step: "
            "bash scripts/download_godot.sh && "
            "export GODOT_BIN=$HOME/godot/Godot_v4.7.2-stable_linux.x86_64",
            file=sys.stderr,
        )
        return ["godot-missing"]

    env = {**os.environ, "GODOT_BIN": godot, "GODOT_MCP_GODOT_BIN": godot}
    proc = subprocess.run(
        ["bash", str(REPO / "scripts" / "diagnose_fixture_smoke.sh")],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        _ok("smoke:diagnose_fixture_smoke")
        return []
    _fail("smoke:diagnose_fixture_smoke", proc.stderr[-500:] or proc.stdout[-500:])
    return ["diagnose-smoke-failed"]


def check_instruction_staleness() -> list[str]:
    # Call the analyzer directly: the CLI exits 1 on known only_python /
    # only_gdscript asymmetries that are upstream-accepted (not drift).
    sys.path.insert(0, str(REPO))
    from evals.instruction_staleness import StaticAnalyzer

    result = StaticAnalyzer(REPO).compare()
    if result["shared"] < 50:
        _fail("eval:instruction_staleness", f"too few shared tools: {result}")
        return ["staleness-failed"]
    if result.get("drift"):
        _fail("eval:instruction_staleness", f"doc/handler drift: {result['drift']}")
        return ["staleness-failed"]
    _ok(
        f"eval:instruction_staleness shared={result['shared']} "
        f"(asymmetries tolerated: only_py={len(result['only_python'])} "
        f"only_gd={len(result['only_gdscript'])})"
    )
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-godot",
        action="store_true",
        help="Skip diagnose smoke (structural + staleness only)",
    )
    args = parser.parse_args()

    failures = check_structural()
    failures.extend(check_instruction_staleness())
    if not args.skip_godot:
        godot_failures = check_diagnose_smoke()
        if godot_failures == ["godot-missing"]:
            # Structural+staleness may still be green; surface blocker distinctly.
            if failures:
                return 1
            return 2
        failures.extend(godot_failures)

    if failures:
        print(f"\n{len(failures)} failure(s).", file=sys.stderr)
        print(
            "For multi-step / LLM agent cases see evals/mt_agent/ "
            "(docs/making-things/agent-evals.md).",
            file=sys.stderr,
        )
        return 1
    print("\nMaking Things trajectory harness: OK")
    print(
        "Note: multi-step agent cases live in evals/mt_agent/ "
        "(mock always; live LLM needs API keys)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
