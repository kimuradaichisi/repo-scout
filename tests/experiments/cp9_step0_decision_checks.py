"""Fixture checks for canonical Decision Identity. No model calls.

The first Step 0.5 failed C3 because a keyword classifier read two identically
decided runs as different: one answered in English, and one sentence's
"repository-wide" belonged to a clause about the model field rather than about
propagation. Case 5 is the direct regression test for that -- the same enum
values with rationales in different languages must compare equal, because the
rationale never reaches the comparison at all.

The negative cases matter as much. Unknown values, missing lines and two
values on one line are all INVALID, and INVALID is never equal to anything,
including another INVALID: certifying "same decision" from two records the
harness could not read is the failure this design exists to prevent.
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
from cp9_decision import INVALID, compare, parse_decision_record

CANONICAL = """\
## DECISION RECORD
domain_model_representation: evidence_result_field
measurement_responsibility: executor_measures
compatibility_strategy: optional_default
propagation_strategy: listed_only

RATIONALE:
An optional field on EvidenceResult keeps every existing construction site
working, and each executor times its own execute() span.
"""

SAME_ENUMS_JAPANESE_RATIONALE = """\
## DECISION RECORD
domain_model_representation: evidence_result_field
measurement_responsibility: executor_measures
compatibility_strategy: optional_default
propagation_strategy: listed_only

RATIONALE:
EvidenceResult に省略可能フィールドを足し、各 executor が自分で計測する。
既存の構築箇所は既定値 None のまま動作する。
"""

ONE_AXIS_DIFFERENT = CANONICAL.replace(
    "measurement_responsibility: executor_measures",
    "measurement_responsibility: common_helper",
)

INVALID_ENUM = CANONICAL.replace(
    "compatibility_strategy: optional_default",
    "compatibility_strategy: optional_with_default",
)

TWO_VALUES = CANONICAL.replace(
    "propagation_strategy: listed_only",
    "propagation_strategy: listed_only, all_sites",
)

MISSING_AXIS = "\n".join(
    line for line in CANONICAL.splitlines() if not line.startswith("propagation_strategy")
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_1_canonical_identical() -> CheckResult:
    result = compare(parse_decision_record(CANONICAL), parse_decision_record(CANONICAL))
    ok = result["identical"] and result["both_valid"]
    return CheckResult("1_canonical_identical_passes", ok, f"{result['matching_axis_count']}/4")


def check_2_one_axis_differs() -> CheckResult:
    result = compare(parse_decision_record(CANONICAL), parse_decision_record(ONE_AXIS_DIFFERENT))
    ok = not result["identical"] and result["matching_axis_count"] == 3
    return CheckResult("2_one_axis_differs_fails", ok, f"{result['matching_axis_count']}/4")


def check_3_invalid_enum() -> CheckResult:
    record = parse_decision_record(INVALID_ENUM)
    result = compare(parse_decision_record(CANONICAL), record)
    ok = record.values["compatibility_strategy"] == INVALID and not result["identical"]
    return CheckResult(
        "3_unknown_enum_is_invalid", ok, f"value={record.values['compatibility_strategy']}"
    )


def check_3b_two_values() -> CheckResult:
    record = parse_decision_record(TWO_VALUES)
    ok = record.values["propagation_strategy"] == INVALID and not record.valid
    return CheckResult(
        "3b_two_values_on_one_line_is_invalid", ok, f"value={record.values['propagation_strategy']}"
    )


def check_4_missing_axis() -> CheckResult:
    record = parse_decision_record(MISSING_AXIS)
    result = compare(parse_decision_record(CANONICAL), record)
    ok = record.values["propagation_strategy"] == INVALID and not result["identical"]
    return CheckResult("4_missing_axis_is_invalid", ok, f"valid={record.valid}")


def check_4b_invalid_never_matches_invalid() -> CheckResult:
    left = parse_decision_record(MISSING_AXIS)
    result = compare(left, parse_decision_record(MISSING_AXIS))
    axis = result["per_axis"]["propagation_strategy"]
    return CheckResult("4b_invalid_never_matches_invalid", not axis["same"], f"same={axis['same']}")


def check_5_rationale_language_ignored() -> CheckResult:
    left = parse_decision_record(CANONICAL)
    right = parse_decision_record(SAME_ENUMS_JAPANESE_RATIONALE)
    ok = compare(left, right)["identical"] and left.rationale != right.rationale
    return CheckResult(
        "5_rationale_language_does_not_affect_verdict", ok, "different rationale, same enums"
    )


def _gate(opus: tuple[int, int], tokens: tuple[int, int], calls: tuple[int, int]) -> dict:
    identity = compare(parse_decision_record(CANONICAL), parse_decision_record(CANONICAL))
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


def check_thresholds_unchanged() -> CheckResult:
    thresholds = registered_thresholds()
    ok = (
        thresholds["C1_opus_token_ratio_min"] == 2.0
        and thresholds["C4a_decision_phase_token_ratio_max"] == 1.50
        and thresholds["C4b_decision_phase_call_ratio_max"] == 2.00
    )
    return CheckResult("thresholds_unchanged_by_revision", ok, f"{thresholds}")


def run_all() -> list[CheckResult]:
    return [
        check_1_canonical_identical(),
        check_2_one_axis_differs(),
        check_3_invalid_enum(),
        check_3b_two_values(),
        check_4_missing_axis(),
        check_4b_invalid_never_matches_invalid(),
        check_5_rationale_language_ignored(),
        check_gate_passes_when_axis_moves(),
        check_gate_fails_on_flat_axis(),
        check_gate_fails_on_growing_decision_phase(),
        check_gate_fails_on_zero_denominator(),
        check_thresholds_unchanged(),
    ]
