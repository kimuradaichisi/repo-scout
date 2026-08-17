"""Fixture checks for the A/B stop rule. No model calls.

The rule decides whether L runs at all, so it is pinned here before M does.
The cases that matter are the boundaries: a tie is not an overtake, one metric
is enough, and CP8's actual shape -- Config B worse on all three -- must not
be mistaken for a crossover. The last case is the whole point of the rule; if
it ever reads CP8's numbers as a reversal, the search would stop at exactly
the volume already known to be too small.
"""

from dataclasses import dataclass
from typing import Any

from cp9_ab_report import compare, execution_totals, next_step, quality_met, reversal


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _run(opus: int, sonnet: int, cost: float, elapsed: float) -> dict[str, Any]:
    """A minimal run report carrying only what the stop rule reads."""
    families = {
        "opus": {"total_tokens": opus, "cost_usd": cost * 0.6},
        "sonnet": {"total_tokens": sonnet, "cost_usd": cost * 0.4},
        "haiku": {"total_tokens": 0, "cost_usd": 0.0},
    }
    return {
        "size": "M",
        "task_key": "m_duration_two_executors",
        "model_usage": families,
        "main_call": {"elapsed_seconds": elapsed, "cost_usd": cost},
        "quality": {"test_pass": True, "gate_pass": True},
        "regression": {"regression_count": 0},
        "scope": {"scope_violation_count": 0, "expected_files_present": True},
        "safety": {"repo_leaks": 0},
    }


# CP8's measured shape at one atomic change: B worse on every axis.
CP8_LIKE_A = _run(opus=195_761, sonnet=0, cost=0.345677, elapsed=60.413)
CP8_LIKE_B = _run(opus=281_426, sonnet=250_195, cost=0.934215, elapsed=206.842)


def check_20_totals_sum_all_families() -> CheckResult:
    totals = execution_totals(CP8_LIKE_B)
    ok = totals["total_tokens"] == 281_426 + 250_195 and totals["elapsed_seconds"] == 206.842
    return CheckResult("20_execution_totals_sum_families", ok, f"{totals}")


def check_21_cp8_shape_is_not_a_reversal() -> CheckResult:
    result = reversal(CP8_LIKE_A, CP8_LIKE_B)
    ok = not result["reversal_detected"] and result["reversed_metrics"] == []
    return CheckResult("21_worse_on_all_three_is_no_reversal", ok, f"{result['reversed_metrics']}")


def check_22_single_metric_triggers() -> CheckResult:
    faster_b = _run(opus=281_426, sonnet=250_195, cost=0.934215, elapsed=30.0)
    result = reversal(CP8_LIKE_A, faster_b)
    ok = result["reversal_detected"] and result["reversed_metrics"] == ["elapsed_seconds"]
    return CheckResult("22_one_metric_is_enough", ok, f"{result['reversed_metrics']}")


def check_23_tie_is_not_a_reversal() -> CheckResult:
    tied = _run(opus=195_761, sonnet=0, cost=0.345677, elapsed=60.413)
    result = reversal(CP8_LIKE_A, tied)
    ok = not result["reversal_detected"]
    return CheckResult("23_tie_is_not_overtaking", ok, f"{result['reversed_metrics']}")


def check_24_all_three_reversed() -> CheckResult:
    cheap_b = _run(opus=50_000, sonnet=40_000, cost=0.10, elapsed=30.0)
    result = reversal(CP8_LIKE_A, cheap_b)
    ok = sorted(result["reversed_metrics"]) == sorted(
        ["total_cost_usd", "total_tokens", "elapsed_seconds"]
    )
    return CheckResult("24_all_three_can_reverse", ok, f"{result['reversed_metrics']}")


def check_25_next_step_routing() -> CheckResult:
    identity = {"identical": True, "matching_axis_count": 3}
    no_reversal = next_step(compare(CP8_LIKE_A, CP8_LIKE_B, identity))
    cheap_b = _run(opus=50_000, sonnet=40_000, cost=0.10, elapsed=30.0)
    with_reversal = next_step(compare(CP8_LIKE_A, cheap_b, identity))
    ok = no_reversal["action"] == "proceed_to_L" and with_reversal["action"] == "stop_and_report"
    return CheckResult(
        "25_next_step_routes_on_reversal",
        ok,
        f"{no_reversal['action']} / {with_reversal['action']}",
    )


def check_26_quality_floor_is_deterministic() -> CheckResult:
    broken = _run(opus=1, sonnet=1, cost=0.1, elapsed=1.0)
    broken["scope"] = {"scope_violation_count": 1, "expected_files_present": True}
    ok = quality_met(CP8_LIKE_A) and not quality_met(broken)
    return CheckResult("26_quality_floor_counts_scope", ok, "one scope violation fails the floor")


def check_27_opus_reduction_and_share() -> CheckResult:
    identity = {"identical": True, "matching_axis_count": 3}
    result = compare(CP8_LIKE_A, CP8_LIKE_B, identity)["roi"]
    expected = round(1 - (281_426 / 195_761), 4)
    ok = result["opus_reduction_vs_A"] == expected and result["main_share_in_B"] is not None
    return CheckResult("27_roi_metrics_computed", ok, f"{result}")


def run_all() -> list[CheckResult]:
    return [
        check_20_totals_sum_all_families(),
        check_21_cp8_shape_is_not_a_reversal(),
        check_22_single_metric_triggers(),
        check_23_tie_is_not_a_reversal(),
        check_24_all_three_reversed(),
        check_25_next_step_routing(),
        check_26_quality_floor_is_deterministic(),
        check_27_opus_reduction_and_share(),
    ]
