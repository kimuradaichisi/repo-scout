"""A/B comparison and the pre-registered stop rule for CP9-v3's M and L runs.

CP9 is looking for the volume at which delegation starts paying for itself.
CP8 measured it losing on all three of cost, tokens and elapsed at a task
volume of roughly one atomic change. The rule below is registered here, before
M runs, and is deliberately one-sided: the search ends the moment Config B
comes from behind on *any* of the three, because that is the crossover the
experiment set out to locate, and running L afterwards would not sharpen it.

Reversal means B overtakes A -- strictly lower cost, or strictly fewer tokens,
or strictly less wall clock. Lower is better on all three, so no metric needs
a direction flag, and ties do not count: an equal figure has not overtaken
anything.

Quality is deterministic here. Gates, regression and scope all come from the
harness, so no grader runs and there is no evaluation cost to separate out of
the execution figures being compared.
"""

from typing import Any

REVERSAL_METRICS = ("total_cost_usd", "total_tokens", "elapsed_seconds")


def _usage_total(report: dict[str, Any], field: str) -> float:
    usage = report["model_usage"]
    return sum(float(usage[family][field]) for family in ("opus", "sonnet", "haiku"))


def execution_totals(report: dict[str, Any]) -> dict[str, float]:
    """What one run cost to produce its result. No grader is involved."""
    return {
        "total_tokens": _usage_total(report, "total_tokens"),
        "total_cost_usd": round(_usage_total(report, "cost_usd"), 6),
        "elapsed_seconds": report["main_call"]["elapsed_seconds"],
    }


def opus_reduction_vs_a(config_a: dict[str, Any], config_b: dict[str, Any]) -> float | None:
    a_opus = int(config_a["model_usage"]["opus"]["total_tokens"])
    b_opus = int(config_b["model_usage"]["opus"]["total_tokens"])
    return None if a_opus <= 0 else round(1 - (b_opus / a_opus), 4)


def main_share_in_b(config_b: dict[str, Any]) -> float | None:
    total = execution_totals(config_b)["total_tokens"]
    opus = int(config_b["model_usage"]["opus"]["total_tokens"])
    return None if not total else round(opus / total, 4)


def quality_floor(report: dict[str, Any]) -> dict[str, Any]:
    """Deterministic quality only: nothing here is anyone's self-report."""
    return {
        "test_pass": report["quality"]["test_pass"],
        "gate_pass": report["quality"]["gate_pass"],
        "regression_count": report["regression"]["regression_count"],
        "scope_violation_count": report["scope"]["scope_violation_count"],
        "expected_files_present": report["scope"]["expected_files_present"],
        "repo_leaks": report["safety"]["repo_leaks"],
    }


def quality_met(report: dict[str, Any]) -> bool:
    floor = quality_floor(report)
    return bool(
        floor["test_pass"]
        and floor["gate_pass"]
        and floor["regression_count"] == 0
        and floor["scope_violation_count"] == 0
        and floor["expected_files_present"]
        and floor["repo_leaks"] == 0
    )


def reversal(config_a: dict[str, Any], config_b: dict[str, Any]) -> dict[str, Any]:
    """Did Config B overtake Config A on cost, tokens or elapsed?"""
    a_totals, b_totals = execution_totals(config_a), execution_totals(config_b)
    per_metric = {
        metric: {
            "config_a": a_totals[metric],
            "config_b": b_totals[metric],
            "delta_b_minus_a": round(b_totals[metric] - a_totals[metric], 6),
            "ratio_b_over_a": (
                round(b_totals[metric] / a_totals[metric], 4) if a_totals[metric] else None
            ),
            "b_overtook_a": b_totals[metric] < a_totals[metric],
        }
        for metric in REVERSAL_METRICS
    }
    reversed_metrics = [name for name, entry in per_metric.items() if entry["b_overtook_a"]]
    return {
        "per_metric": per_metric,
        "reversed_metrics": reversed_metrics,
        "reversal_detected": bool(reversed_metrics),
        "rule": "stop after this size when B is strictly lower on any of cost/tokens/elapsed",
    }


def compare(config_a: dict[str, Any], config_b: dict[str, Any], identity: dict[str, Any]) -> dict:
    """One size's A/B comparison, with the stop rule evaluated on it."""
    return {
        "size": config_a["size"],
        "task_key": config_a["task_key"],
        "quality": {
            "config_a": quality_floor(config_a),
            "config_b": quality_floor(config_b),
            "config_a_met": quality_met(config_a),
            "config_b_met": quality_met(config_b),
            "b_at_least_a": quality_met(config_b) >= quality_met(config_a),
        },
        "roi": {
            "opus_reduction_vs_A": opus_reduction_vs_a(config_a, config_b),
            "main_share_in_B": main_share_in_b(config_b),
        },
        "reversal": reversal(config_a, config_b),
        "decision_identity_a_vs_b": identity,
        "execution_totals": {
            "config_a": execution_totals(config_a),
            "config_b": execution_totals(config_b),
        },
    }


def next_step(comparison: dict[str, Any]) -> dict[str, Any]:
    """M reversing ends the search; M not reversing sends it to L."""
    reversed_here = comparison["reversal"]["reversal_detected"]
    return {
        "size_completed": comparison["size"],
        "reversal_detected": reversed_here,
        "reversed_metrics": comparison["reversal"]["reversed_metrics"],
        "action": "stop_and_report" if reversed_here else "proceed_to_L",
    }
