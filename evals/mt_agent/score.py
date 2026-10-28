"""Tool-accuracy scoring for Making Things agent trajectories.

Morph of the consumer "tool-accuracy eval" pattern (expected_tools spec) from
Godot Editor MCP consumer docs — score calls against a pinned subsequence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    result: Any = None
    error: str | None = None


@dataclass
class ScoreResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    called: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reasons": self.reasons,
            "called": self.called,
        }


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    if not needle:
        return True
    i = 0
    for name in haystack:
        if name == needle[i]:
            i += 1
            if i == len(needle):
                return True
    return False


def score_trajectory(
    calls: list[ToolCall],
    *,
    required_subsequence: list[str],
    pass_criteria: list[str] | None = None,
) -> ScoreResult:
    """Pass when required tools appear in order; apply lightweight criteria checks."""
    called = [c.name for c in calls]
    reasons: list[str] = []
    if not _is_subsequence(required_subsequence, called):
        reasons.append(
            f"required_subsequence not found in order: {required_subsequence} vs {called}"
        )

    criteria = pass_criteria or []
    if "live_mutate_reports_persisted_false" in criteria:
        live = [c for c in calls if c.name == "godot_runtime_set_live_property"]
        if not live:
            reasons.append("no godot_runtime_set_live_property call")
        else:
            for c in live:
                data = c.result if isinstance(c.result, dict) else {}
                if data.get("persisted") is True:
                    reasons.append(f"live mutate claimed persisted=true: {data}")
                # Mock path stamps persisted=false on success payloads.
                if c.ok and data and data.get("persisted") is not False:
                    # Allow missing persisted only when dry_run preview omitted it —
                    # still require honesty when present.
                    if "persisted" in data and data["persisted"] is not False:
                        reasons.append("persisted must be false for live mutate")

    if "dry_run_or_undo_present" in criteria:
        live = [c for c in calls if c.name == "godot_runtime_set_live_property"]
        if live and not any(
            (c.arguments or {}).get("dry_run")
            or (isinstance(c.result, dict) and c.result.get("previous_value") is not None)
            for c in live
        ):
            reasons.append("expected dry_run or previous_value on live mutate")

    if "parse_errors_empty_after_fix" in criteria:
        parse_calls = [c for c in calls if c.name == "godot_scripts_get_parse_errors"]
        if len(parse_calls) < 2:
            reasons.append("need ≥2 get_parse_errors calls (before + after fix)")
        else:
            last = parse_calls[-1]
            data = last.result if isinstance(last.result, dict) else {}
            errors = data.get("errors")
            if errors:
                reasons.append(f"parse errors remain after fix: {errors}")
            if last.ok is False:
                reasons.append("final get_parse_errors failed")

    if "never_claim_success_while_errors" in criteria:
        # Structural: if any get_parse_errors returned errors, a later clean
        # re-check must appear in the trajectory.
        saw_errors = False
        for c in calls:
            if c.name == "godot_scripts_get_parse_errors":
                data = c.result if isinstance(c.result, dict) else {}
                errs = data.get("errors") or []
                if errs or data.get("ok") is False:
                    saw_errors = True
        if saw_errors and not any(
            c.name == "godot_scripts_get_parse_errors"
            and isinstance(c.result, dict)
            and c.result.get("ok") is True
            and not c.result.get("errors")
            for c in calls
        ):
            reasons.append("saw parse errors but never re-checked clean")

    if "import_reports_ok_or_pending" in criteria:
        imports = [c for c in calls if c.name == "godot_asset_import_asset"]
        if not imports:
            reasons.append("missing godot_asset_import_asset")
        elif not any(c.ok for c in imports):
            reasons.append("import tool failed")

    return ScoreResult(passed=not reasons, reasons=reasons, called=called)
