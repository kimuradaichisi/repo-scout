"""Model-free validation for M5's measurement code, before spending C0/C1.

Nothing here starts a Claude process. It proves the duplicate/overlap
detector, pack-call parser, and interpretation vocabulary behave correctly
on synthetic transcripts before the two real runs (Control, Pack First)
happen -- the only two model calls M5 is allowed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m5_compare import compare
from m5_pack_calls import (
    final_direct_reads_after_pack,
    pack_call_count,
    pack_call_metrics,
    reposcout_call_count,
)
from m5_read_analysis import fictional_read_paths, read_events, repeat_metrics


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _assistant_read(tool_use_id: str, file_path: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "Read",
                    "input": {"file_path": file_path},
                }
            ]
        },
    }


def _assistant_bash(tool_use_id: str, command: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "Bash",
                    "input": {"command": command},
                }
            ]
        },
    }


def _user_result(tool_use_id: str, content: str) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}]
        },
    }


def _numbered(start: int, end: int) -> str:
    return "\n".join(f"{n}\ttext{n}" for n in range(start, end + 1))


def check_01_exact_duplicate_read_counts_once() -> CheckResult:
    root = Path("/repo")
    events = [
        _assistant_read("t1", "/repo/a.py"),
        _user_result("t1", _numbered(1, 5)),
        _assistant_read("t2", "/repo/a.py"),
        _user_result("t2", _numbered(1, 5)),
    ]
    metrics = repeat_metrics(read_events(events, root))
    ok = metrics["repeated_read_calls"] == 1 and metrics["repeated_source_bytes"] > 0
    return CheckResult("01_exact_duplicate_read_counts_once", ok, str(metrics))


def check_02_non_overlapping_reads_are_not_repeated() -> CheckResult:
    root = Path("/repo")
    events = [
        _assistant_read("t1", "/repo/a.py"),
        _user_result("t1", _numbered(1, 5)),
        _assistant_read("t2", "/repo/a.py"),
        _user_result("t2", _numbered(10, 15)),
    ]
    metrics = repeat_metrics(read_events(events, root))
    ok = metrics["repeated_read_calls"] == 0 and metrics["range_overlap_bytes"] == 0
    return CheckResult("02_non_overlapping_reads_are_not_repeated", ok, str(metrics))


def check_03_partial_overlap_is_counted_without_exact_match() -> CheckResult:
    root = Path("/repo")
    events = [
        _assistant_read("t1", "/repo/a.py"),
        _user_result("t1", _numbered(1, 10)),
        _assistant_read("t2", "/repo/a.py"),
        _user_result("t2", _numbered(6, 15)),
    ]
    metrics = repeat_metrics(read_events(events, root))
    ok = metrics["repeated_read_calls"] == 0 and metrics["range_overlap_bytes"] > 0
    return CheckResult("03_partial_overlap_is_counted_without_exact_match", ok, str(metrics))


def check_04_different_paths_never_repeat() -> CheckResult:
    root = Path("/repo")
    events = [
        _assistant_read("t1", "/repo/a.py"),
        _user_result("t1", _numbered(1, 5)),
        _assistant_read("t2", "/repo/b.py"),
        _user_result("t2", _numbered(1, 5)),
    ]
    metrics = repeat_metrics(read_events(events, root))
    ok = metrics["repeated_read_calls"] == 0 and metrics["range_overlap_bytes"] == 0
    return CheckResult("04_different_paths_never_repeat", ok, str(metrics))


def check_05_changed_content_is_not_a_duplicate() -> CheckResult:
    root = Path("/repo")
    events = [
        _assistant_read("t1", "/repo/a.py"),
        _user_result("t1", _numbered(1, 5)),
        _assistant_read("t2", "/repo/a.py"),
        _user_result("t2", "1\tCHANGED\n2\ttext2\n3\ttext3\n4\ttext4\n5\ttext5"),
    ]
    metrics = repeat_metrics(read_events(events, root))
    ok = metrics["repeated_read_calls"] == 0
    return CheckResult("05_changed_content_is_not_a_duplicate", ok, str(metrics))


def check_06_fictional_read_path_detected() -> CheckResult:
    root = Path("/repo")
    events = [_assistant_read("t1", "/repo/ghost.py"), _user_result("t1", _numbered(1, 3))]
    fictional = fictional_read_paths(read_events(events, root), ["a.py"])
    ok = fictional == ["ghost.py"]
    return CheckResult("06_fictional_read_path_detected", ok, str(fictional))


def check_07_pack_call_detected_and_not_confused_with_skeleton() -> CheckResult:
    events = [
        _assistant_bash("t1", "reposcout skeleton --root ."),
        _user_result("t1", "a.py\nb.py"),
        _assistant_bash("t2", "reposcout pack /tmp/req.yaml --root ."),
        _user_result(
            "t2",
            '{"sources": [], "metrics": {"packed_source_bytes": 100, '
            '"duplicate_or_overlap_bytes_eliminated": 40, "requested_ranges": 2, '
            '"packed_ranges": 1, "requested_source_bytes": 140, "unique_paths": 1, '
            '"pack_chars": 90}}',
        ),
    ]
    ok = pack_call_count(events) == 1
    metrics = pack_call_metrics(events)
    ok = ok and metrics == {"packed_source_bytes": 100, "duplicate_or_overlap_bytes_eliminated": 40}
    return CheckResult("07_pack_call_detected_and_not_confused_with_skeleton", ok, str(metrics))


def check_07b_path_mentioning_reposcout_is_not_a_call() -> CheckResult:
    """Regression: M5's live control run hit this -- the snapshot path itself
    contains "reposcout" (/tmp/reposcout-m5-.../target), so `find`/`grep`
    naming that path must not be counted as invoking the CLI."""
    events = [
        _assistant_bash("t1", "find /tmp/reposcout-m5-20260818/control/target -maxdepth 2"),
        _user_result("t1", "src\ntests"),
        _assistant_bash("t2", 'grep -rl "CONTEXT_LINES" /tmp/reposcout-m5-20260818/control/target'),
        _user_result("t2", "ripgrep.py"),
    ]
    ok = pack_call_count(events) == 0 and reposcout_call_count(events) == 0
    return CheckResult(
        "07b_path_mentioning_reposcout_is_not_a_call",
        ok,
        f"pack={pack_call_count(events)} reposcout={reposcout_call_count(events)}",
    )


def check_08_reads_after_pack_are_counted() -> CheckResult:
    events = [
        _assistant_read("t0", "/repo/a.py"),
        _user_result("t0", _numbered(1, 3)),
        _assistant_bash("t1", "reposcout pack /tmp/req.yaml --root ."),
        _user_result("t1", '{"sources": [], "metrics": {}}'),
        _assistant_read("t2", "/repo/b.py"),
        _user_result("t2", _numbered(1, 3)),
    ]
    ok = final_direct_reads_after_pack(events) == 1
    return CheckResult(
        "08_reads_after_pack_are_counted", ok, f"count={final_direct_reads_after_pack(events)}"
    )


def _fake_report(*, repeated: int, bytes_: int, tokens: int, coverage: float) -> dict[str, Any]:
    return {
        "primary_metrics": {
            "repeated_read_calls": repeated,
            "repeated_source_bytes": bytes_,
            "total_input_tokens": tokens,
        },
        "secondary_metrics": {"cost_usd": 0.1, "elapsed_seconds": 10.0},
        "quality": {"quality_floor_met": coverage >= 1.0},
        "run": {"exit_code": 0, "error": ""},
    }


def check_09_all_three_reduced_is_observed_reduction() -> CheckResult:
    c0 = _fake_report(repeated=3, bytes_=900, tokens=50000, coverage=1.0)
    c1 = _fake_report(repeated=0, bytes_=0, tokens=30000, coverage=1.0)
    result = compare(c0, c1)["interpretation"]
    return CheckResult(
        "09_all_three_reduced_is_observed_reduction", result == "observed reduction", result
    )


def check_10_nothing_reduced_is_no_observed_reduction() -> CheckResult:
    c0 = _fake_report(repeated=0, bytes_=0, tokens=30000, coverage=1.0)
    c1 = _fake_report(repeated=0, bytes_=0, tokens=30000, coverage=1.0)
    result = compare(c0, c1)["interpretation"]
    return CheckResult(
        "10_nothing_reduced_is_no_observed_reduction", result == "no observed reduction", result
    )


def check_11_reduction_without_quality_parity_is_mixed_not_success() -> CheckResult:
    c0 = _fake_report(repeated=3, bytes_=900, tokens=50000, coverage=1.0)
    c1 = _fake_report(repeated=0, bytes_=0, tokens=30000, coverage=0.5)
    result = compare(c0, c1)["interpretation"]
    return CheckResult(
        "11_reduction_without_quality_parity_is_mixed_not_success", result == "mixed", result
    )


def check_12_failed_run_is_measurement_invalid() -> CheckResult:
    c0 = _fake_report(repeated=3, bytes_=900, tokens=50000, coverage=1.0)
    c1 = _fake_report(repeated=0, bytes_=0, tokens=30000, coverage=1.0)
    c1["run"]["exit_code"] = 1
    result = compare(c0, c1)["interpretation"]
    return CheckResult(
        "12_failed_run_is_measurement_invalid", result == "measurement invalid", result
    )


ALL_CHECKS = (
    check_01_exact_duplicate_read_counts_once,
    check_02_non_overlapping_reads_are_not_repeated,
    check_03_partial_overlap_is_counted_without_exact_match,
    check_04_different_paths_never_repeat,
    check_05_changed_content_is_not_a_duplicate,
    check_06_fictional_read_path_detected,
    check_07_pack_call_detected_and_not_confused_with_skeleton,
    check_07b_path_mentioning_reposcout_is_not_a_call,
    check_08_reads_after_pack_are_counted,
    check_09_all_three_reduced_is_observed_reduction,
    check_10_nothing_reduced_is_no_observed_reduction,
    check_11_reduction_without_quality_parity_is_mixed_not_success,
    check_12_failed_run_is_measurement_invalid,
)
