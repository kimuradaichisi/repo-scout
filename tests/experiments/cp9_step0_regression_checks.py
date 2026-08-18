"""Fixture checks for regression measurement. No model calls, no Claude.

Check 9 is the one that matters most. CP8 ran pytest as `-v --tb=no -q`, the
two flags cancelled, no per-test line was printed, and the regression metric
was silently always zero. So this builds a throwaway package, runs the real
pytest three times at three different console verbosities, and requires the
parsed outcomes to be identical every time. A metric that changes with a
display flag is not measuring the code.

The other cases pin the definition itself: a test that passed and now fails is
a regression, a test that did not exist at baseline is not, and a green run
before and after yields zero.
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cp9_gates import PASSED, parse_junit_xml, regression_report

BASELINE_SOURCE = """\
def test_kept_passing():
    assert True


def test_will_break():
    assert True
"""

CHANGED_SOURCE = """\
def test_kept_passing():
    assert True


def test_will_break():
    assert False


def test_added_later():
    assert True
"""


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _run_pytest(workdir: Path, source: str, extra: list[str]) -> dict[str, str]:
    """Write one test module, run pytest, and read its XML. XML lives outside workdir."""
    (workdir / "tests").mkdir(parents=True, exist_ok=True)
    (workdir / "tests" / "test_sample.py").write_text(source, encoding="utf-8")
    xml = Path(tempfile.mkdtemp(prefix="cp9-junit-")) / "report.xml"
    subprocess.run(
        ["python", "-m", "pytest", "tests", f"--junitxml={xml}", "-p", "no:cacheprovider", *extra],
        cwd=workdir,
        text=True,
        capture_output=True,
        check=False,
    )
    return parse_junit_xml(xml)


def _workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="cp9-regression-"))


def check_6_no_regression_when_all_still_pass() -> CheckResult:
    workdir = _workdir()
    before = _run_pytest(workdir, BASELINE_SOURCE, ["-q"])
    after = _run_pytest(workdir, BASELINE_SOURCE, ["-q"])
    report = regression_report(before, after)
    ok = report["regression_count"] == 0 and len(before) == 2
    return CheckResult(
        "6_baseline_pass_to_post_pass_is_zero", ok, f"count={report['regression_count']}"
    )


def check_7_broken_test_is_one_regression() -> CheckResult:
    workdir = _workdir()
    before = _run_pytest(workdir, BASELINE_SOURCE, ["-q"])
    after = _run_pytest(workdir, CHANGED_SOURCE, ["-q"])
    report = regression_report(before, after)
    ok = report["regression_count"] == 1 and report["regression_ids"] == [
        "tests.test_sample::test_will_break"
    ]
    return CheckResult("7_baseline_pass_to_post_fail_is_one", ok, f"ids={report['regression_ids']}")


def check_8_new_test_is_not_a_regression() -> CheckResult:
    workdir = _workdir()
    before = _run_pytest(workdir, BASELINE_SOURCE, ["-q"])
    after = _run_pytest(workdir, CHANGED_SOURCE, ["-q"])
    report = regression_report(before, after)
    ok = report["new_test_ids"] == ["tests.test_sample::test_added_later"] and (
        "tests.test_sample::test_added_later" not in report["regression_ids"]
    )
    return CheckResult("8_new_test_not_counted", ok, f"new={report['new_test_ids']}")


def check_9_independent_of_console_verbosity() -> CheckResult:
    workdir = _workdir()
    variants = {
        "-q": _run_pytest(workdir, BASELINE_SOURCE, ["-q"]),
        "-v": _run_pytest(workdir, BASELINE_SOURCE, ["-v"]),
        "-v --tb=no -q": _run_pytest(workdir, BASELINE_SOURCE, ["-v", "--tb=no", "-q"]),
    }
    reference = variants["-q"]
    differing = [flag for flag, outcomes in variants.items() if outcomes != reference]
    ok = not differing and len(reference) == 2 and set(reference.values()) == {PASSED}
    return CheckResult(
        "9_outcomes_independent_of_verbosity", ok, f"parsed={len(reference)} differing={differing}"
    )


def run_all() -> list[CheckResult]:
    return [
        check_6_no_regression_when_all_still_pass(),
        check_7_broken_test_is_one_regression(),
        check_8_new_test_is_not_a_regression(),
        check_9_independent_of_console_verbosity(),
    ]
