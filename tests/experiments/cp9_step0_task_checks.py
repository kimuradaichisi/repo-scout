"""Static validation of the CP9 task family. No model calls.

These checks are what stands between "S/M/L were designed to differ only in
volume" and it actually being true of the files that will be handed to a run.
They are deliberately mechanical: the decision text has to be byte-identical
across sizes, the target lists have to name paths that exist (or, for new test
files, that do not yet), and target and forbidden lists must not overlap --
a path that is both in scope and out of scope makes the scope metric
meaningless in whichever direction the run happens to go.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cp9_tasks import DECISION_STATEMENT, TASKS, all_criteria, render_goal

NEW_FILE_PREFIX = "tests/unit/"


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_decision_count() -> CheckResult:
    counts = {task["size"]: task["decision_count"] for task in TASKS}
    ok = all(value == 1 for value in counts.values())
    return CheckResult("decision_count_is_one", ok, f"{counts}")


def check_decision_text_identical() -> CheckResult:
    """Every size must state the judgement in exactly the same words."""
    prefixes = {render_goal(task).split("ただし**今回実装するのは")[0] for task in TASKS}
    ok = len(prefixes) == 1 and DECISION_STATEMENT in prefixes.pop()
    return CheckResult(
        "decision_text_identical_across_sizes", ok, f"distinct decision prefixes: {1 if ok else 2}"
    )


def check_volume_monotonic() -> CheckResult:
    vectors = [(task["size"], task["volume"]) for task in TASKS]
    keys = ("v1", "v2", "v3", "v4", "v5")
    failures = [
        key for key in keys if not (vectors[0][1][key] < vectors[1][1][key] < vectors[2][1][key])
    ]
    detail = ", ".join(f"{size}={vector}" for size, vector in vectors)
    return CheckResult("volume_vector_strictly_increasing", not failures, f"{detail}")


def check_expected_matches_targets() -> CheckResult:
    mismatched = [
        task["size"]
        for task in TASKS
        if sorted(task["targets"]) != sorted(task["expected_changed_files"])
    ]
    return CheckResult(
        "expected_changed_files_equals_targets", not mismatched, f"mismatched sizes: {mismatched}"
    )


def _target_path_problem(repo_root: Path, path: str) -> str | None:
    exists = (repo_root / path).exists()
    if path.startswith(NEW_FILE_PREFIX):
        return None if not exists else f"{path} already exists but is declared new"
    return None if exists else f"{path} does not exist in the repository"


def check_target_paths(repo_root: Path) -> CheckResult:
    problems = [
        problem
        for task in TASKS
        for path in task["targets"]
        if (problem := _target_path_problem(repo_root, path))
    ]
    return CheckResult("target_paths_valid", not problems, f"{problems or 'all target paths ok'}")


def check_forbidden_paths(repo_root: Path) -> CheckResult:
    missing = [
        path
        for task in TASKS
        for path in task["forbidden_paths"]
        if not (repo_root / path).exists()
    ]
    return CheckResult(
        "forbidden_paths_exist", not missing, f"{missing or 'all forbidden paths exist'}"
    )


def check_scope_disjoint() -> CheckResult:
    overlaps = [
        f"{task['size']}:{path}"
        for task in TASKS
        for path in task["targets"]
        if any(path.startswith(bad) for bad in task["forbidden_paths"])
    ]
    return CheckResult("target_and_forbidden_disjoint", not overlaps, f"{overlaps or 'disjoint'}")


def check_criteria_separation() -> CheckResult:
    problems = []
    for task in TASKS:
        outcome, contract = set(task["outcome_criteria"]), set(task["contract_criteria"])
        if not outcome or not contract:
            problems.append(f"{task['size']}: empty criteria group")
        if outcome & contract:
            problems.append(f"{task['size']}: overlapping criteria")
        if len(all_criteria(task)) != len(set(all_criteria(task))):
            problems.append(f"{task['size']}: duplicate criterion")
    return CheckResult(
        "outcome_and_contract_criteria_separated", not problems, f"{problems or 'ok'}"
    )


def run_all(repo_root: Path) -> list[CheckResult]:
    return [
        check_decision_count(),
        check_decision_text_identical(),
        check_volume_monotonic(),
        check_expected_matches_targets(),
        check_target_paths(repo_root),
        check_forbidden_paths(repo_root),
        check_scope_disjoint(),
        check_criteria_separation(),
    ]


def summary(results: list[CheckResult]) -> dict[str, Any]:
    return {
        "checks": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in results],
        "all_passed": all(r.passed for r in results),
    }
