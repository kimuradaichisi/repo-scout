"""The Axis Validity Gate, with its thresholds fixed before Step 0.5 runs.

CP9 only means anything if S and L differ in how much work there is and not
in how hard the thinking was. This module is where that claim is made
falsifiable, and it is written before the two Config A runs precisely so the
numbers cannot be chosen once the results are visible.

Why these thresholds:

C1  A_opus(L) >= 2.0 x A_opus(S)   -- given in the CP9 charter. Below this the
    axis has not moved enough for a crossover search to mean anything: CP8's
    handoff floor sits at ~291k Opus tokens, and the 0.50 reduction criterion
    needs ~583k, so S and L have to be at least a factor of two apart before
    they can bracket anything.

C4a decision_phase_input_cache(L) <= 1.5 x that of S. The decision is stated in
    identical words at both sizes and declared repository-wide, so its cost
    ought to be flat (ratio 1.0). What legitimately grows is reading: L's
    investigation covers five executor files where S's covers one, and those
    files are 25-68 lines, so four extra reads add on the order of 2-4k tokens
    against a decision phase measured in tens of thousands. Cache-read
    accumulation makes a few extra turns superlinear, so 1.5 leaves room for
    roughly 20% more decision turns. It matters that 1.5 < 2.0: if C1 and C4a
    both hold, the implementation phase grew strictly faster than the decision
    phase, which is the claim "we varied execution volume, not uncertainty".

C4b decision_phase_tool_calls(L) <= 2.0 x that of S. Tool calls in a decision
    phase are small integers -- CP8's Config A runs took 10-19 requests in
    total -- so the ratio is coarse and a stricter bound would fail on a
    two-call difference. 2.0 still catches a decision phase that doubled in
    effort.

C4c decision-phase elapsed ratio is reported, not gated. Wall clock carries
    queueing and rate-limit noise that has nothing to do with the axis; it is
    here to contradict the token figures if something is wrong, not to decide.

A gate that cannot be computed (a missing figure, a zero denominator) fails.
CP9 stops on FAIL and the task sizes are not retuned and retried -- refitting
the tasks until the axis validates would be fitting the experiment to the
answer.
"""

from dataclasses import dataclass
from typing import Any

OPUS_TOKEN_RATIO_MIN = 2.0
DECISION_PHASE_TOKEN_RATIO_MAX = 1.50
DECISION_PHASE_CALL_RATIO_MAX = 2.00
REQUIRED_DECISION_COUNT = 1


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    observed: float | None
    threshold: float | None
    detail: str


def _ratio(large: float, small: float) -> float | None:
    if small <= 0:
        return None
    return round(large / small, 4)


def check_opus_growth(small_opus: int, large_opus: int) -> GateCheck:
    ratio = _ratio(large_opus, small_opus)
    return GateCheck(
        name="C1_opus_token_growth",
        passed=ratio is not None and ratio >= OPUS_TOKEN_RATIO_MIN,
        observed=ratio,
        threshold=OPUS_TOKEN_RATIO_MIN,
        detail=f"A_opus S={small_opus} L={large_opus}, need L/S >= {OPUS_TOKEN_RATIO_MIN}",
    )


def check_decision_count(small_count: int, large_count: int) -> GateCheck:
    ok = small_count == large_count == REQUIRED_DECISION_COUNT
    return GateCheck(
        name="C2_decision_count",
        passed=ok,
        observed=None,
        threshold=REQUIRED_DECISION_COUNT,
        detail=f"decision_count S={small_count} L={large_count}, both must equal 1",
    )


def check_decision_identity(comparison: dict[str, Any]) -> GateCheck:
    ok = bool(comparison.get("identical")) and bool(comparison.get("both_complete"))
    matched = comparison.get("matching_axis_count")
    return GateCheck(
        name="C3_decision_identity",
        passed=ok,
        observed=float(matched) if isinstance(matched, int) else None,
        threshold=4.0,
        detail=f"{matched}/4 axes identical; both_complete={comparison.get('both_complete')}",
    )


def check_decision_phase_tokens(small_tokens: int, large_tokens: int) -> GateCheck:
    ratio = _ratio(large_tokens, small_tokens)
    return GateCheck(
        name="C4a_decision_phase_tokens",
        passed=ratio is not None and ratio <= DECISION_PHASE_TOKEN_RATIO_MAX,
        observed=ratio,
        threshold=DECISION_PHASE_TOKEN_RATIO_MAX,
        detail=(
            f"decision-phase input+cache S={small_tokens} L={large_tokens}, "
            f"need L/S <= {DECISION_PHASE_TOKEN_RATIO_MAX}"
        ),
    )


def check_decision_phase_calls(small_calls: int, large_calls: int) -> GateCheck:
    ratio = _ratio(large_calls, small_calls)
    return GateCheck(
        name="C4b_decision_phase_tool_calls",
        passed=ratio is not None and ratio <= DECISION_PHASE_CALL_RATIO_MAX,
        observed=ratio,
        threshold=DECISION_PHASE_CALL_RATIO_MAX,
        detail=(
            f"decision-phase tool calls S={small_calls} L={large_calls}, "
            f"need L/S <= {DECISION_PHASE_CALL_RATIO_MAX}"
        ),
    )


def evaluate(checks: list[GateCheck], elapsed_ratio: float | None) -> dict[str, Any]:
    return {
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "observed": check.observed,
                "threshold": check.threshold,
                "detail": check.detail,
            }
            for check in checks
        ],
        "reported_only": {"C4c_decision_phase_elapsed_ratio": elapsed_ratio},
        "axis_valid": all(check.passed for check in checks),
    }


def registered_thresholds() -> dict[str, Any]:
    """Recorded into every artifact so a run can be checked against the rule it ran under."""
    return {
        "C1_opus_token_ratio_min": OPUS_TOKEN_RATIO_MIN,
        "C2_required_decision_count": REQUIRED_DECISION_COUNT,
        "C3_decision_identity_axes_required": 4,
        "C4a_decision_phase_token_ratio_max": DECISION_PHASE_TOKEN_RATIO_MAX,
        "C4b_decision_phase_call_ratio_max": DECISION_PHASE_CALL_RATIO_MAX,
        "C4c_decision_phase_elapsed_ratio": "reported, not gated",
    }
