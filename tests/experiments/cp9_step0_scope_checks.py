"""Fixture checks for allowlist-based scope. No model calls.

Check 12 is the reason the metric was rewritten. Under forbidden-prefix
scoring, one unexpected file scored a violation at S (six prefixes out of
scope) and zero at L (two), so the same behaviour was penalised at one size
and invisible at the other while CP9 was busy comparing the two. Here the
identical intrusion is injected at every size and has to score identically,
even though allowed_paths is 3 entries at S and 11 at L.

Check 13 covers the case the first Step 0.5 actually produced: the L run
created two scratch files, emptied them, and reported that the sandbox would
not let it delete them. Those files stayed in the working tree and scored
nothing. They score now.
"""

from dataclasses import dataclass

from cp9_scope import scope_report
from cp9_tasks import TASKS, get_size

SCRATCH_FILES = (".limits_check.py", "tests/unit/test_smoke_scratch.py")


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_10_allowed_only_is_clean() -> CheckResult:
    problems = []
    for task in TASKS:
        report = scope_report(list(task["allowed_paths"]), task)
        if report["scope_violation_count"] != 0 or not report["expected_files_present"]:
            problems.append(f"{task['size']}: {report['scope_violation_count']} violations")
    return CheckResult("10_allowed_paths_only_is_zero", not problems, f"{problems or 'ok'}")


def check_11_one_unexpected_file() -> CheckResult:
    problems = []
    for task in TASKS:
        changed = [*task["allowed_paths"], "src/reposcout/runner.py"]
        report = scope_report(changed, task)
        if report["scope_violation_count"] != 1:
            problems.append(f"{task['size']}: {report['scope_violation_count']}")
    return CheckResult("11_one_unexpected_file_is_one", not problems, f"{problems or 'ok'}")


def check_12_same_meaning_across_sizes() -> CheckResult:
    """One identical intrusion must score identically at S, M and L."""
    counts = {}
    for size in ("S", "M", "L"):
        task = get_size(size)
        report = scope_report([*task["allowed_paths"], "intruder.py"], task)
        counts[size] = (len(task["allowed_paths"]), report["scope_violation_count"])
    violations = {count for _, count in counts.values()}
    allowed_sizes = {allowed for allowed, _ in counts.values()}
    ok = violations == {1} and len(allowed_sizes) == 3
    return CheckResult("12_same_meaning_across_sizes", ok, f"(allowed, violations)={counts}")


def check_13_scratch_files_are_violations() -> CheckResult:
    task = get_size("L")
    report = scope_report([*task["allowed_paths"], *SCRATCH_FILES], task)
    ok = report["scope_violation_count"] == 2 and report["scope_violation_paths"] == sorted(
        SCRATCH_FILES
    )
    return CheckResult("13_leftover_scratch_is_violation", ok, f"{report['scope_violation_paths']}")


def check_14_missing_target_is_not_a_scope_violation() -> CheckResult:
    """A target never touched is a contract miss, reported separately from scope."""
    task = get_size("M")
    changed = list(task["allowed_paths"])[:-1]
    report = scope_report(changed, task)
    ok = report["scope_violation_count"] == 0 and not report["expected_files_present"]
    return CheckResult(
        "14_missing_target_separate_from_scope", ok, f"missing={report['missing_target_paths']}"
    )


def run_all() -> list[CheckResult]:
    return [
        check_10_allowed_only_is_clean(),
        check_11_one_unexpected_file(),
        check_12_same_meaning_across_sizes(),
        check_13_scratch_files_are_violations(),
        check_14_missing_target_is_not_a_scope_violation(),
    ]
