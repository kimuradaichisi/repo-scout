"""Fixture checks for Decision Identity and the Axis Validity Gate. No model calls.

Both mechanisms decide whether a CP9 point is usable, so both have to be shown
to fail when they should. The cases that matter here are the negative ones: a
record missing an axis, a sentence that could be read two ways, and two
unreadable records being compared to each other. The last is the trap -- two
UNCLEAR values are equal as strings, and treating that as agreement would let
CP9 certify "same decision" precisely when it could not read either decision.
"""

from dataclasses import dataclass

from cp9_axis_gate import (
    check_decision_count,
    check_decision_identity,
    check_decision_phase_calls,
    check_decision_phase_tokens,
    check_opus_growth,
    evaluate,
    registered_thresholds,
)
from cp9_decision import UNCLEAR, compare, parse_decision_record

WELL_FORMED = """\
## DECISION RECORD
DOMAIN MODEL REPRESENTATION: EvidenceResult に duration_ms フィールドを追加する
MEASUREMENT RESPONSIBILITY: 各 executor が自分で計測する
COMPATIBILITY STRATEGY: 省略可能フィールドとし既定値を持たせる
PROPAGATION STRATEGY: 列挙された対象のみに適用し、残りは後続作業とする

## DECISIONS
理由をここに書く。
"""

MISSING_AXIS = """\
## DECISION RECORD
DOMAIN MODEL REPRESENTATION: EvidenceResult に duration_ms フィールドを追加する
MEASUREMENT RESPONSIBILITY: 各 executor が自分で計測する
COMPATIBILITY STRATEGY: 省略可能フィールドとし既定値を持たせる
"""

AMBIGUOUS = WELL_FORMED.replace(
    "EvidenceResult に duration_ms フィールドを追加する",
    "EvidenceResult ではなく別のモデルを作る",
)

DIFFERENT = WELL_FORMED.replace("各 executor が自分で計測する", "run_command が計測する").replace(
    "列挙された対象のみに適用し、残りは後続作業とする", "全 executor に一律で適用する"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_parses_four_axes() -> CheckResult:
    record = parse_decision_record(WELL_FORMED)
    ok = record.complete and record.readable
    return CheckResult("decision_record_parses_four_axes", ok, f"{record.categories}")


def check_missing_axis_incomplete() -> CheckResult:
    record = parse_decision_record(MISSING_AXIS)
    return CheckResult(
        "missing_axis_is_incomplete", not record.complete, f"complete={record.complete}"
    )


def check_ambiguous_is_unclear() -> CheckResult:
    record = parse_decision_record(AMBIGUOUS)
    value = record.categories["domain_model_representation"]
    return CheckResult("ambiguous_sentence_is_unclear", value == UNCLEAR, f"category={value}")


def check_identical_records_match() -> CheckResult:
    result = compare(parse_decision_record(WELL_FORMED), parse_decision_record(WELL_FORMED))
    return CheckResult(
        "identical_records_compare_identical",
        bool(result["identical"]),
        f"matching_axes={result['matching_axis_count']}",
    )


def check_different_records_differ() -> CheckResult:
    result = compare(parse_decision_record(WELL_FORMED), parse_decision_record(DIFFERENT))
    ok = not result["identical"] and result["matching_axis_count"] == 2
    return CheckResult(
        "different_records_compare_different", ok, f"matching_axes={result['matching_axis_count']}"
    )


def check_unclear_never_matches() -> CheckResult:
    result = compare(parse_decision_record(AMBIGUOUS), parse_decision_record(AMBIGUOUS))
    axis = result["per_axis"]["domain_model_representation"]
    return CheckResult(
        "unclear_does_not_count_as_agreement", not axis["same"], f"same={axis['same']}"
    )


def _gate(opus: tuple[int, int], tokens: tuple[int, int], calls: tuple[int, int]) -> dict:
    identity = compare(parse_decision_record(WELL_FORMED), parse_decision_record(WELL_FORMED))
    checks = [
        check_opus_growth(*opus),
        check_decision_count(1, 1),
        check_decision_identity(identity),
        check_decision_phase_tokens(*tokens),
        check_decision_phase_calls(*calls),
    ]
    return evaluate(checks, elapsed_ratio=1.0)


def check_gate_passes_when_axis_moves() -> CheckResult:
    result = _gate((200_000, 600_000), (50_000, 60_000), (10, 14))
    return CheckResult(
        "gate_passes_on_valid_axis", bool(result["axis_valid"]), "3.0x / 1.2x / 1.4x"
    )


def check_gate_fails_on_flat_axis() -> CheckResult:
    result = _gate((200_000, 300_000), (50_000, 60_000), (10, 14))
    failed = [c["name"] for c in result["checks"] if not c["passed"]]
    ok = not result["axis_valid"] and failed == ["C1_opus_token_growth"]
    return CheckResult("gate_fails_on_flat_axis", ok, f"failed={failed}")


def check_gate_fails_on_growing_decision_phase() -> CheckResult:
    result = _gate((200_000, 600_000), (50_000, 120_000), (10, 14))
    failed = [c["name"] for c in result["checks"] if not c["passed"]]
    ok = not result["axis_valid"] and failed == ["C4a_decision_phase_tokens"]
    return CheckResult("gate_fails_on_growing_decision_phase", ok, f"failed={failed}")


def check_gate_fails_on_zero_denominator() -> CheckResult:
    result = _gate((0, 600_000), (50_000, 60_000), (10, 14))
    return CheckResult(
        "gate_fails_when_ratio_undefined", not result["axis_valid"], "S opus = 0 must not pass"
    )


def check_thresholds_recorded() -> CheckResult:
    thresholds = registered_thresholds()
    ok = thresholds["C1_opus_token_ratio_min"] == 2.0 and (
        thresholds["C4a_decision_phase_token_ratio_max"] == 1.50
    )
    return CheckResult("thresholds_pre_registered", ok, f"{thresholds}")


def run_all() -> list[CheckResult]:
    return [
        check_parses_four_axes(),
        check_missing_axis_incomplete(),
        check_ambiguous_is_unclear(),
        check_identical_records_match(),
        check_different_records_differ(),
        check_unclear_never_matches(),
        check_gate_passes_when_axis_moves(),
        check_gate_fails_on_flat_axis(),
        check_gate_fails_on_growing_decision_phase(),
        check_gate_fails_on_zero_denominator(),
        check_thresholds_recorded(),
    ]
