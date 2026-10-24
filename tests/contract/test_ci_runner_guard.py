"""Contract test: fork PRs must not run on a self-hosted runner (issue #650).

Making Things (MT-3): ``ci.yml`` / ``e2e.yml`` default to GitHub-hosted
``ubuntu-latest`` (via ``MT_CI_RUNS_ON`` / ``MT_E2E_RUNS_ON``) so jobs are not
stuck queued without hybridindie labels. When the owner sets those vars to a
self-hosted label set, the same fork-PR guard must still apply — this pins it
so a new job can't be added without the guard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_E2E = _REPO_ROOT / ".github" / "workflows" / "e2e.yml"

# The fork distinction: a same-repo PR's head repo is this repo; a fork's is not.
_FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
_MT_RUNS_ON = "MT_CI_RUNS_ON"
_MT_E2E_RUNS_ON = "MT_E2E_RUNS_ON"


def _jobs(path: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast("dict[str, dict[str, Any]]", data["jobs"])


def test_every_ci_job_skips_fork_prs() -> None:
    offenders = []
    for name, job in _jobs(_CI).items():
        condition = str(job.get("if", ""))
        # Must run on non-PR events (push to main) and same-repo PRs only.
        if "github.event_name != 'pull_request'" not in condition or _FORK_GUARD not in condition:
            offenders.append(name)
    assert not offenders, (
        "every ci.yml job must carry the fork-PR guard (issue #650); missing: "
        + ", ".join(offenders)
    )


def test_ci_jobs_use_mt_runs_on_override() -> None:
    """Making Things: jobs default via MT_CI_RUNS_ON (ubuntu-latest) and can
    switch to self-hosted without editing YAML — fork guard still applies."""
    for name, job in _jobs(_CI).items():
        runs_on = str(job.get("runs-on"))
        assert _MT_RUNS_ON in runs_on, (
            f"{name}: runs-on must use fromJSON(vars.MT_CI_RUNS_ON || …); got {runs_on}"
        )
        assert "ubuntu-latest" in runs_on, (
            f"{name}: default runs-on must include ubuntu-latest fallback; got {runs_on}"
        )


def test_e2e_guard_matches_ci_guard() -> None:
    """Both workflows protect runners with the same fork-PR predicate."""
    e2e = _jobs(_E2E)["editor-suites"]
    assert _FORK_GUARD in str(e2e.get("if", ""))
    runs_on = str(e2e.get("runs-on"))
    assert _MT_E2E_RUNS_ON in runs_on or _MT_RUNS_ON in runs_on
    assert "ubuntu-latest" in runs_on


def test_no_stale_test_count_comment() -> None:
    """The '642-test suite' comments are stale (#650): the suite is far larger and
    the number drifts every PR — don't hard-code a count."""
    text = _CI.read_text(encoding="utf-8")
    assert "642-test" not in text
