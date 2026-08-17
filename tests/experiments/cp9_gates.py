"""Quality gates for CP9, with regression read from structured test results.

CP8's gate runner inferred which tests passed by matching `PASSED` lines in
pytest's console output, and ran pytest as `-v --tb=no -q`. Those two flags
cancel (verbosity = 1 - 1 = 0), so no per-test line is ever printed, the
passing-id set was always empty, and `regression_count = len(empty - empty)`
was structurally zero. It could not have detected a regression. CP9 stops
parsing prose and reads pytest's JUnit XML instead, which is emitted the same
way at every console verbosity.

The XML is written outside the snapshot on purpose. A report file dropped into
the working tree would show up as a changed path and be counted as a scope
violation -- the harness would be manufacturing the violation it measures.

CP8's own gate module is left untouched, and CP8's recorded regression_count
is not recomputed. It is historically non-informative, and saying so is the
correction; rewriting the artifact would not be.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class GateResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class GateReport:
    pytest_: GateResult
    ruff_check: GateResult
    ruff_format_check: GateResult
    mypy: GateResult
    outcomes: dict[str, str]

    @property
    def gate_pass(self) -> bool:
        return (
            self.pytest_.passed
            and self.ruff_check.passed
            and self.ruff_format_check.passed
            and self.mypy.passed
        )

    @property
    def test_pass(self) -> bool:
        return self.pytest_.passed


def _run(command: list[str], snapshot: Path) -> GateResult:
    completed = subprocess.run(
        command, cwd=snapshot, text=True, capture_output=True, check=False, timeout=300
    )
    return GateResult(" ".join(command), completed.returncode, completed.stdout, completed.stderr)


def _case_status(case: ElementTree.Element) -> str:
    if case.find("failure") is not None or case.find("error") is not None:
        return FAILED
    if case.find("skipped") is not None:
        return SKIPPED
    return PASSED


def parse_junit_xml(path: Path) -> dict[str, str]:
    """node id -> passed/failed/skipped. Empty when pytest wrote no report."""
    if not path.exists():
        return {}
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return {}
    outcomes: dict[str, str] = {}
    for case in root.iter("testcase"):
        node_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        outcomes[node_id] = _case_status(case)
    return outcomes


def run_gates(snapshot: Path, xml_path: Path) -> GateReport:
    """Run the four gates. xml_path must live outside the snapshot."""
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    xml_path.unlink(missing_ok=True)
    pytest_result = _run(["uv", "run", "pytest", "-q", f"--junitxml={xml_path}"], snapshot)
    return GateReport(
        pytest_=pytest_result,
        ruff_check=_run(["uv", "run", "ruff", "check", "."], snapshot),
        ruff_format_check=_run(["uv", "run", "ruff", "format", "--check", "."], snapshot),
        mypy=_run(["uv", "run", "mypy", "src"], snapshot),
        outcomes=parse_junit_xml(xml_path),
    )


def regression_report(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    """Tests that passed at baseline and fail after the change.

    A test absent from the baseline is new, not a regression. A baseline test
    absent afterwards is recorded separately: deleting a passing test is a real
    failure mode, but it is not what the pre-registered definition counts, and
    quietly folding it in would change the metric rather than report it.
    """
    regression_ids = sorted(
        node_id
        for node_id, status in before.items()
        if status == PASSED and after.get(node_id) == FAILED
    )
    disappeared = sorted(
        node_id for node_id, status in before.items() if status == PASSED and node_id not in after
    )
    return {
        "baseline_test_ids": sorted(before),
        "post_change_test_ids": sorted(after),
        "baseline_status": dict(sorted(before.items())),
        "post_change_status": dict(sorted(after.items())),
        "regression_ids": regression_ids,
        "regression_count": len(regression_ids),
        "new_test_ids": sorted(set(after) - set(before)),
        "disappeared_baseline_pass_ids": disappeared,
    }


def gate_summary(report: GateReport) -> dict[str, Any]:
    return {
        "test_pass": report.test_pass,
        "gate_pass": report.gate_pass,
        "pytest_passed": report.pytest_.passed,
        "ruff_check_passed": report.ruff_check.passed,
        "ruff_format_check_passed": report.ruff_format_check.passed,
        "mypy_passed": report.mypy.passed,
        "collected_test_count": len(report.outcomes),
        "passing_test_count": sum(1 for s in report.outcomes.values() if s == PASSED),
    }
