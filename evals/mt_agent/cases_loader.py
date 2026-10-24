"""Load Making Things agent eval case YAML fixtures."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).resolve().parent / "cases"


@dataclass
class EvalCase:
    id: str
    title: str
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    required_subsequence: list[str] = field(default_factory=list)
    pass_criteria: list[str] = field(default_factory=list)
    mock_script: list[dict[str, Any]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    related_docs: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def load_case(path: Path) -> EvalCase:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "id" not in data:
        raise ValueError(f"invalid case file: {path}")
    return EvalCase(
        id=str(data["id"]),
        title=str(data.get("title", data["id"])),
        prompt=str(data.get("prompt", "")).strip(),
        expected_tools=list(data.get("expected_tools") or []),
        required_subsequence=list(data.get("required_subsequence") or []),
        pass_criteria=list(data.get("pass_criteria") or []),
        mock_script=list(data.get("mock_script") or []),
        skills=list(data.get("skills") or []),
        prompts=list(data.get("prompts") or []),
        related_docs=list(data.get("related_docs") or []),
        raw=data,
    )


def iter_cases(cases_dir: Path | None = None) -> list[EvalCase]:
    root = cases_dir or CASES_DIR
    paths = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))
    return [load_case(p) for p in paths]


def get_case(case_id: str, cases_dir: Path | None = None) -> EvalCase:
    for case in iter_cases(cases_dir):
        if case.id == case_id:
            return case
    raise KeyError(f"unknown case id: {case_id}")
