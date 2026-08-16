"""Hard-gate evaluation and cross-config aggregation for CP8 Step 1.

Per-run hard gates decide whether a run is a valid data point at all --
rev.2 was explicit that a run failing these is a setup failure, not a model
quality result, so a failed hard gate must be visible before anyone reads the
comparison numbers next to it. Aggregation only runs for a task once both its
Config A and Config B runs exist and passed their hard gates; a broken pairing
produces no ratio rather than a misleading one computed against a null.
"""

from typing import Any

COMMON_HARD_GATES = (
    "test_pass",
    "gate_pass",
    "acceptance_criteria_met",
)


def evaluate_hard_gates(report: dict[str, Any], is_config_b: bool) -> dict[str, Any]:
    quality = report["quality"]
    checks = {name: bool(quality[name]) for name in COMMON_HARD_GATES}
    checks["regression_count_zero"] = quality["regression_count"] == 0
    checks["diff_scope_violation_count_zero"] = quality["diff_scope_violation_count"] == 0
    checks["repo_leaks_zero"] = report["safety"]["repo_leaks"] == 0
    checks["active_config_propagated"] = report["active_config"]["matches_expected"]

    if is_config_b:
        role = report["main_role"]
        usage = report["model_usage"]
        checks["main_direct_write_count_zero"] = role["main_direct_write_count"] == 0
        checks["pre_worker_diff_empty"] = role["pre_worker_diff_empty"] is True
        checks["worker_model_is_sonnet"] = usage["sonnet"]["total_tokens"] > 0
        checks["main_model_is_opus"] = usage["opus"]["total_tokens"] > 0

    return {"checks": checks, "all_passed": all(checks.values())}


def opus_reduction_vs_a(
    config_a_report: dict[str, Any], config_b_report: dict[str, Any]
) -> float | None:
    a_opus = int(config_a_report["model_usage"]["opus"]["total_tokens"])
    b_opus = int(config_b_report["model_usage"]["opus"]["total_tokens"])
    if a_opus <= 0:
        return None
    return round(1 - (b_opus / a_opus), 4)


def _production_cost(report: dict[str, Any]) -> dict[str, float | int]:
    usage = report["model_usage"]
    total_tokens = (
        usage["opus"]["total_tokens"]
        + usage["sonnet"]["total_tokens"]
        + usage["haiku"]["total_tokens"]
    )
    total_cost = (
        usage["opus"]["cost_usd"] + usage["sonnet"]["cost_usd"] + usage["haiku"]["cost_usd"]
    )
    return {"total_tokens": total_tokens, "total_cost_usd": round(total_cost, 6)}


def compare_task(
    config_a_report: dict[str, Any], config_b_report: dict[str, Any]
) -> dict[str, Any]:
    """One task's A/B comparison. No success direction assumed for cost/tokens."""
    a_cost = _production_cost(config_a_report)
    b_cost = _production_cost(config_b_report)
    a_elapsed = config_a_report["main_call"]["elapsed_seconds"]
    b_elapsed = config_b_report["main_call"]["elapsed_seconds"]

    return {
        "task_key": config_a_report["task_key"],
        "opus_reduction_vs_a": opus_reduction_vs_a(config_a_report, config_b_report),
        "main_share_in_b": (
            round(
                config_b_report["model_usage"]["opus"]["total_tokens"] / b_cost["total_tokens"], 4
            )
            if b_cost["total_tokens"]
            else None
        ),
        "total_tokens": {"config_a": a_cost["total_tokens"], "config_b": b_cost["total_tokens"]},
        "total_cost_usd": {
            "config_a": a_cost["total_cost_usd"],
            "config_b": b_cost["total_cost_usd"],
        },
        "elapsed_seconds": {"config_a": a_elapsed, "config_b": b_elapsed},
        "quality_parity": {
            "config_a_hard_gates_passed": config_a_report["hard_gates"]["all_passed"],
            "config_b_hard_gates_passed": config_b_report["hard_gates"]["all_passed"],
        },
    }


def go_no_go(comparisons: list[dict[str, Any]], b_reports: list[dict[str, Any]]) -> dict[str, Any]:
    quality_parity = all(c["quality_parity"]["config_b_hard_gates_passed"] for c in comparisons)
    reductions = [
        c["opus_reduction_vs_a"] for c in comparisons if c["opus_reduction_vs_a"] is not None
    ]
    reduction_met_count = sum(1 for r in reductions if r >= 0.50)
    no_direct_write = all(r["main_role"]["main_direct_write_count"] == 0 for r in b_reports)
    no_scope_violation = all(r["main_role"]["worker_scope_violation_count"] == 0 for r in b_reports)

    return {
        "1_quality_parity": quality_parity,
        "2_opus_reduction_2_of_3": reduction_met_count >= 2,
        "2_opus_reduction_detail": reductions,
        "3_main_did_not_implement": no_direct_write,
        "4_worker_no_scope_violation": no_scope_violation,
        "go": quality_parity
        and reduction_met_count >= 2
        and no_direct_write
        and no_scope_violation,
    }
