"""Authoritative, harness-run quality gates for a CP8 Step 1 run.

Main's and the Worker's own reports of "tests pass" are claims, not
measurements -- Step 0 already showed the Worker will say so honestly when it
can, but review_gate_match exists specifically to catch the case where a
claim and reality diverge, and that requires a check that does not come from
either party. This module runs the same four gates the prompts ask for, but
from the harness, before and after a task, and treats its own result as
ground truth: test_pass / gate_pass / regression_count are computed here, not
parsed out of anyone's prose.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PASSED_LINE = re.compile(r"^(?P<node>\S+::\S+)\s+PASSED", re.MULTILINE)
FAILED_LINE = re.compile(r"^(?P<node>\S+::\S+)\s+FAILED", re.MULTILINE)


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
    passing_test_ids: frozenset[str]

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
        command, cwd=snapshot, text=True, capture_output=True, check=False, timeout=180
    )
    return GateResult(" ".join(command), completed.returncode, completed.stdout, completed.stderr)


def _passing_test_ids(pytest_result: GateResult) -> frozenset[str]:
    return frozenset(PASSED_LINE.findall(pytest_result.stdout))


def run_gates(snapshot: Path) -> GateReport:
    """Run all four gates and record which individual tests passed."""
    pytest_result = _run(["uv", "run", "pytest", "-v", "--tb=no", "-q"], snapshot)
    return GateReport(
        pytest_=pytest_result,
        ruff_check=_run(["uv", "run", "ruff", "check", "."], snapshot),
        ruff_format_check=_run(["uv", "run", "ruff", "format", "--check", "."], snapshot),
        mypy=_run(["uv", "run", "mypy", "src"], snapshot),
        passing_test_ids=_passing_test_ids(pytest_result),
    )


def regression_count(before: GateReport, after: GateReport) -> int:
    """Tests that passed before the task and no longer pass after it."""
    return len(before.passing_test_ids - after.passing_test_ids)


def gate_summary(report: GateReport) -> dict[str, bool | int]:
    return {
        "test_pass": report.test_pass,
        "gate_pass": report.gate_pass,
        "pytest_passed": report.pytest_.passed,
        "ruff_check_passed": report.ruff_check.passed,
        "ruff_format_check_passed": report.ruff_format_check.passed,
        "mypy_passed": report.mypy.passed,
        "passing_test_count": len(report.passing_test_ids),
    }
