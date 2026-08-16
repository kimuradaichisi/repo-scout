"""Per-run metric assembly for CP8 Step 1.

Each function here takes recorded artifacts (a transcript, a git diff, a gate
report) and produces one clearly-scoped slice of the final report -- model
usage, Worker behaviour, Main role adherence, or safety -- so a run's report
can be built by composing them rather than by one function reaching into
everything at once. cross-config figures (opus_reduction_vs_A) are not
computed here: they need both configs' results for the same task side by
side, which only the orchestrator (run_cp8_step1.py) holds.

quality_metrics's acceptance_criteria_met is deliberately the AND of two
independent halves. deterministic_criteria_met (gates, regressions, scope,
and the required files existing) is fact, not judgement, and settles on its
own; the grader's overall_met is the one semantic question -- does the diff's
*content* actually satisfy each criterion -- that no deterministic check here
can answer. A run that passes every gate but ships an empty test file fails
on the grader half; a run the grader likes but that leaves a gate red fails
on the deterministic half. evaluation_metrics keeps the grader's own token/
cost/elapsed figures out of quality entirely, so they never get folded into
Main/Worker's execution cost (model_usage, main_call) by accident.
"""

from pathlib import Path
from typing import Any

from claude_metrics import ClaudeRun
from cp8_step1_gates import GateReport, gate_summary, regression_count
from cp8_step1_review import (
    active_config_propagation,
    delegation_rounds,
    diff_scope_violation_count,
    main_direct_write_count,
    pre_worker_diff_empty,
    review_gate_match,
    rework_cycles,
    unknown_blocked_count,
    worker_scope_violation_count,
)
from cp8_transcript import load_events
from cp8_worker_metrics import model_separation, worker_metrics, worker_permission_denial_count
from run_comparison import count_repo_leaks


def _tokens(entry: Any, *names: str) -> int:
    if not isinstance(entry, dict):
        return 0
    return sum(int(entry.get(name, 0) or 0) for name in names)


def _model_total_tokens(usage: dict[str, Any], keyword: str) -> dict[str, int | float]:
    """input/output/cache/total tokens for every model whose name matches keyword."""
    matches = {name: entry for name, entry in usage.items() if keyword in name.lower()}
    input_t = sum(_tokens(e, "inputTokens", "input_tokens") for e in matches.values())
    output_t = sum(_tokens(e, "outputTokens", "output_tokens") for e in matches.values())
    cache_r = sum(
        _tokens(e, "cacheReadInputTokens", "cache_read_input_tokens") for e in matches.values()
    )
    cache_c = sum(
        _tokens(e, "cacheCreationInputTokens", "cache_creation_input_tokens")
        for e in matches.values()
    )
    cost = sum(float(e.get("costUSD", 0.0) or 0.0) for e in matches.values() if isinstance(e, dict))
    return {
        "input_tokens": input_t,
        "output_tokens": output_t,
        "cache_read_tokens": cache_r,
        "cache_creation_tokens": cache_c,
        "total_tokens": input_t + output_t + cache_r + cache_c,
        "cost_usd": round(cost, 6),
    }


def model_usage_breakdown(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Every model's token/cost share of one run, split by keyword family."""
    separation = model_separation(events)
    usage = separation["raw_model_usage"]
    known = {"opus", "sonnet", "haiku"}
    other = {
        name: entry
        for name, entry in usage.items()
        if not any(keyword in name.lower() for keyword in known)
    }
    return {
        "opus": _model_total_tokens(usage, "opus"),
        "sonnet": _model_total_tokens(usage, "sonnet"),
        "haiku": _model_total_tokens(usage, "haiku"),
        "other": {"models": sorted(other), "raw": other},
        "models_observed": separation["models_observed"],
    }


def expected_files_present(changed_paths: list[str], task: dict[str, Any]) -> bool:
    """Deterministic floor: did every file the task names as required actually change?"""
    return all(expected in changed_paths for expected in task["expected_changed_files"])


def _deterministic_floor(
    gate: dict[str, bool | int], regression: int, diff_violation: int, files_present: bool
) -> bool:
    return (
        bool(gate["test_pass"])
        and bool(gate["gate_pass"])
        and regression == 0
        and diff_violation == 0
        and files_present
    )


def quality_metrics(
    before: GateReport,
    after: GateReport,
    changed_paths: list[str],
    task: dict[str, Any],
    grade: dict[str, Any],
) -> dict[str, Any]:
    """acceptance_criteria_met = deterministic_criteria_met AND grader.overall_met."""
    gate = gate_summary(after)
    regression = regression_count(before, after)
    diff_violation = diff_scope_violation_count(changed_paths, task)
    files_present = expected_files_present(changed_paths, task)
    deterministic_met = _deterministic_floor(gate, regression, diff_violation, files_present)
    return {
        **gate,
        "regression_count": regression,
        "diff_scope_violation_count": diff_violation,
        "expected_files_present": files_present,
        "deterministic_criteria_met": deterministic_met,
        "grader_verdict": {
            "overall_met": grade["overall_met"],
            "criteria": grade["criteria"],
            "parse_error": grade["parse_error"],
        },
        "acceptance_criteria_met": deterministic_met and grade["overall_met"],
    }


def evaluation_metrics(grade: dict[str, Any]) -> dict[str, Any]:
    """Grader resource usage — separate from Main/Worker's own execution cost."""
    return {"grader": grade["call"]}


def worker_behavior_metrics(
    events: list[dict[str, Any]], pack_paths: frozenset[str]
) -> dict[str, Any]:
    metrics = worker_metrics(events, pack_paths)
    return {
        "worker_read_count": metrics.worker_read_count,
        "worker_search_count": metrics.worker_search_count,
        "worker_write_count": metrics.worker_write_count,
        "worker_outside_pack_read_count": metrics.worker_outside_pack_read_count,
        "worker_fallback_exploration_volume": metrics.worker_fallback_exploration_volume,
        "worker_permission_denial_count": worker_permission_denial_count(events),
        "worker_tool_calls": metrics.worker_tool_calls,
    }


def main_role_metrics(
    events: list[dict[str, Any]],
    main_role_log: str,
    pre_worker_log: str,
    changed_paths: list[str],
    authoritative_gate_pass: bool,
) -> dict[str, Any]:
    rounds = delegation_rounds(events)
    result_text = rounds[-1].result_pack_text if rounds else ""
    return {
        "main_direct_write_count": main_direct_write_count(main_role_log),
        "pre_worker_diff_empty": pre_worker_diff_empty(pre_worker_log),
        "review_gate_match": review_gate_match(result_text, authoritative_gate_pass)
        if rounds
        else None,
        "rework_cycles": rework_cycles(events),
        "unknown_blocked_count": unknown_blocked_count(result_text) if rounds else 0,
        "worker_scope_violation_count": worker_scope_violation_count(
            [r.pack_text for r in rounds], changed_paths
        ),
        "delegation_rounds": len(rounds),
    }


def active_config_check(role_log: str, expected_config: str) -> dict[str, Any]:
    """Did CP8_ACTIVE_CONFIG reach the hook as this run's harness call set it?

    Computed for both configs: Config A's role gate log should show only
    config_a among its ALLOW entries just as reliably as Config B's should
    show only config_b.
    """
    return active_config_propagation(role_log, expected_config)


def safety_metrics(transcript: Path, repo_root: Path) -> dict[str, Any]:
    return {"repo_leaks": count_repo_leaks(transcript, repo_root)}


def run_call_metrics(run: ClaudeRun) -> dict[str, Any]:
    return {
        "input_tokens": run.total_input_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": round(run.cost_usd, 6),
        "elapsed_seconds": round(run.wall_seconds, 3),
        "exit_code": run.exit_code,
        "permission_denials": len(run.permission_denials),
    }


def load_run_events(transcript: Path) -> list[dict[str, Any]]:
    return load_events(transcript)
