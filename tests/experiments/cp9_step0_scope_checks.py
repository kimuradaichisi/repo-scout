"""Fixture checks for allowlist scope and the v3 Execution Scope record. No model calls.

Checks 10-14 cover the measurement rewritten in v2. Check 12 is the reason it
was rewritten: under forbidden-prefix scoring one unexpected file scored a
violation at S (six prefixes out of scope) and zero at L (two), so the same
behaviour was penalised at one size and invisible at the other while CP9 was
comparing the two. The identical intrusion is injected at every size here and
has to score identically despite allowlists of 3, 6 and 11 entries.

Checks 17-19 cover the v3 split. Execution Scope has to carry the full volume
vector, has to differ across sizes, and has to be marked as never feeding the
Axis Validity Gate -- the confusion that invalidated v2 was a scope fact being
scored as a decision, and the record now says which it is.
"""

from dataclasses import dataclass

from cp9_decision import parse_decision_record
from cp9_execution_scope import VOLUME_KEYS, execution_scope, scope_differences
from cp9_scope import scope_report
from cp9_tasks import TASKS, get_size

SCRATCH_FILES = (".limits_check.py", "tests/unit/test_smoke_scratch.py")

RECORD_LISTED_ONLY = """\
domain_model_representation: evidence_result_field
measurement_responsibility: executor_measures
compatibility_strategy: optional_default
propagation_strategy: listed_only
"""
RECORD_ALL_SITES = RECORD_LISTED_ONLY.replace("listed_only", "all_sites")


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
        report = scope_report([*task["allowed_paths"], "src/reposcout/runner.py"], task)
        if report["scope_violation_count"] != 1:
            problems.append(f"{task['size']}: {report['scope_violation_count']}")
    return CheckResult("11_one_unexpected_file_is_one", not problems, f"{problems or 'ok'}")


def check_12_same_meaning_across_sizes() -> CheckResult:
    counts = {}
    for size in ("S", "M", "L"):
        task = get_size(size)
        report = scope_report([*task["allowed_paths"], "intruder.py"], task)
        counts[size] = (len(task["allowed_paths"]), report["scope_violation_count"])
    ok = {count for _, count in counts.values()} == {1} and len(
        {allowed for allowed, _ in counts.values()}
    ) == 3
    return CheckResult("12_same_meaning_across_sizes", ok, f"(allowed, violations)={counts}")


def check_13_scratch_files_are_violations() -> CheckResult:
    task = get_size("L")
    report = scope_report([*task["allowed_paths"], *SCRATCH_FILES], task)
    ok = report["scope_violation_count"] == 2 and report["scope_violation_paths"] == sorted(
        SCRATCH_FILES
    )
    return CheckResult("13_leftover_scratch_is_violation", ok, f"{report['scope_violation_paths']}")


def check_14_missing_target_is_not_a_scope_violation() -> CheckResult:
    task = get_size("M")
    report = scope_report(list(task["allowed_paths"])[:-1], task)
    ok = report["scope_violation_count"] == 0 and not report["expected_files_present"]
    return CheckResult(
        "14_missing_target_separate_from_scope", ok, f"missing={report['missing_target_paths']}"
    )


def check_17_execution_scope_carries_volume() -> CheckResult:
    problems = []
    for task in TASKS:
        scope = execution_scope(task, parse_decision_record(RECORD_LISTED_ONLY))
        missing = [label for label in VOLUME_KEYS.values() if label not in scope["volume"]]
        if missing or not scope["target_list"] or not scope["allowed_paths"]:
            problems.append(f"{task['size']}: missing {missing}")
        if scope["used_for_decision_identity"] is not False:
            problems.append(f"{task['size']}: not marked excluded from identity")
    return CheckResult("17_execution_scope_carries_volume", not problems, f"{problems or 'ok'}")


def check_18_execution_scope_differs_by_size() -> CheckResult:
    small = execution_scope(get_size("S"), parse_decision_record(RECORD_LISTED_ONLY))
    large = execution_scope(get_size("L"), parse_decision_record(RECORD_ALL_SITES))
    diff = scope_differences(small, large)
    ok = (
        diff["allowed_path_count"] == [3, 11]
        and diff["declared_propagation_strategy"] == ["listed_only", "all_sites"]
        and diff["used_for_axis_validity"] is False
        and diff["volume"]["v1_planned_atomic_changes"] == {"left": 3, "right": 11}
    )
    return CheckResult(
        "18_execution_scope_differs_by_size", ok, f"allowed={diff['allowed_path_count']}"
    )


def check_19_scope_declaration_recorded_not_scored() -> CheckResult:
    """The declaration is preserved per run and flagged as excluded from identity."""
    scope = execution_scope(get_size("L"), parse_decision_record(RECORD_ALL_SITES))
    ok = (
        scope["declared_propagation_strategy"] == "all_sites"
        and scope["used_for_decision_identity"] is False
    )
    return CheckResult(
        "19_scope_declaration_recorded_not_scored",
        ok,
        f"declared={scope['declared_propagation_strategy']}",
    )


def run_all() -> list[CheckResult]:
    return [
        check_10_allowed_only_is_clean(),
        check_11_one_unexpected_file(),
        check_12_same_meaning_across_sizes(),
        check_13_scratch_files_are_violations(),
        check_14_missing_target_is_not_a_scope_violation(),
        check_17_execution_scope_carries_volume(),
        check_18_execution_scope_differs_by_size(),
        check_19_scope_declaration_recorded_not_scored(),
    ]
