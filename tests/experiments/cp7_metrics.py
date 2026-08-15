"""Scoring and metric aggregation for the CP7 family of runs.

Split out of run_cp7_task.py so CP7-E (Main-owned planning, no separate
planner call) can report the same metric set without copying the CP7/CP7-D
runner. Orchestration lives in the run_* scripts; only measurement and
aggregation live here.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TEST_GAP_PATTERN = re.compile(
    r"(テスト|test).{0,40}(存在しない|無い|ない|不在|未整備|不足|見つから|なし)"
)


@dataclass(frozen=True)
class CallTokens:
    """Input/output tokens for one model call (zero when a stage is absent)."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class StageTokens:
    first_main: CallTokens
    final_main: CallTokens
    planner: CallTokens
    cost_usd: float
    elapsed_seconds: float


def score_generic(text: str, task: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    expected_files = task["expected_files"]
    expected_symbols = task["expected_symbols"]
    expected_extended = task.get("expected_extended", [])

    found_files = [item for item in expected_files if item.lower() in lowered]
    found_symbols = [item for item in expected_symbols if item.lower() in lowered]
    found_extended = [item for item in expected_extended if item.lower() in lowered]

    expected_total = len(expected_files) + len(expected_symbols) + len(expected_extended)
    found_total = len(found_files) + len(found_symbols) + len(found_extended)

    return {
        "found_files": found_files,
        "missing_files": [item for item in expected_files if item not in found_files],
        "found_symbols": found_symbols,
        "missing_symbols": [item for item in expected_symbols if item not in found_symbols],
        "found_extended": found_extended,
        "missing_extended": [item for item in expected_extended if item not in found_extended],
        "coverage": round(found_total / expected_total, 3) if expected_total else 1.0,
        "mentions_test_gap": bool(TEST_GAP_PATTERN.search(text)),
        "answer_chars": len(text),
    }


def _enclosing_consumer_present(quality: dict[str, Any]) -> bool | None:
    """Whether the Target -> Enclosing Symbol -> Consumer chain was reported.

    None when the task declares no expected_extended items, so "absent" and
    "not applicable" stay distinguishable.
    """
    tracked = quality["found_extended"] + quality["missing_extended"]
    if not tracked:
        return None
    return not quality["missing_extended"]


def build_totals(
    quality: dict[str, Any],
    scout: dict[str, Any],
    path_categories: dict[str, Any],
    tokens: StageTokens,
    meta: dict[str, Any],
) -> dict[str, Any]:
    query_count = meta["query_count"]
    main_input = tokens.first_main.input_tokens + tokens.final_main.input_tokens
    main_output = tokens.first_main.output_tokens + tokens.final_main.output_tokens

    return {
        "coverage": quality["coverage"],
        "planner_model": meta["planner_model"],
        "plan_policy_applied": meta["plan_policy_applied"],
        "main_opus_input_tokens": main_input,
        "main_opus_output_tokens": main_output,
        "main_first_call_input_tokens": tokens.first_main.input_tokens,
        "main_first_call_output_tokens": tokens.first_main.output_tokens,
        "main_final_call_input_tokens": tokens.final_main.input_tokens,
        "main_final_call_output_tokens": tokens.final_main.output_tokens,
        # Kept under the original key names for schema parity with earlier CP7
        # results; planner_* is the model-neutral name. Both are 0 when the
        # planner stage is absent (CP7-E).
        "explorer_sonnet_input_tokens": tokens.planner.input_tokens,
        "explorer_sonnet_output_tokens": tokens.planner.output_tokens,
        "planner_input_tokens": tokens.planner.input_tokens,
        "planner_output_tokens": tokens.planner.output_tokens,
        "total_input_tokens": main_input + tokens.planner.input_tokens,
        "total_output_tokens": main_output + tokens.planner.output_tokens,
        "total_cost_usd": round(tokens.cost_usd, 6),
        "elapsed_seconds": round(tokens.elapsed_seconds, 3),
        "reposcout_query_count": query_count,
        "effective_query_count": scout.get("effective_query_count", 0),
        "effective_query_rate": (
            round(scout.get("effective_query_count", 0) / query_count, 3) if query_count else 0.0
        ),
        "failed_query_count": scout.get("failed_query_count", 0),
        "empty_evidence_count": scout.get("empty_evidence_count", 0),
        "evidence_chars": scout.get("evidence_chars", 0),
        "nonexistent_path_count": path_categories["nonexistent_path_count"],
        "nonexistent_paths": path_categories["nonexistent_paths"],
        "out_of_scope_path_count": path_categories["out_of_scope_path_count"],
        "out_of_scope_paths": path_categories["out_of_scope_paths"],
        "target_enclosing_consumer_evidence_present": _enclosing_consumer_present(quality),
        # B3.2 and its CP7 descendants have no Explorer synthesis stage, so
        # nothing between RepoScout and Main can call a tool -- structurally 0.
        "explorer_additional_tool_calls": 0,
        "repo_leaks": meta["repo_leaks"],
    }


def parse_plan_queries(plan_text: str) -> tuple[list[dict[str, Any]], dict[str, int], str]:
    """Return (queries, tool_breakdown, parse_error) for a generated Plan."""
    try:
        parsed = yaml.safe_load(plan_text)
    except yaml.YAMLError as exc:
        return [], {}, str(exc)

    queries = parsed.get("queries", []) if isinstance(parsed, dict) else []
    breakdown: dict[str, int] = {}
    for query in queries:
        if not isinstance(query, dict):
            continue
        tool = str(query.get("tool", "ornith(unspecified)"))
        breakdown[tool] = breakdown.get(tool, 0) + 1
    return queries, breakdown, ""


@dataclass(frozen=True)
class PlanArtifacts:
    """What the planning stage produced, however many calls it took."""

    handoff: str
    plan_path: Path
    queries: list[dict[str, Any]] = field(default_factory=list)
    tool_breakdown: dict[str, int] = field(default_factory=dict)
    plan_error: str = ""


def build_result(
    task: dict[str, Any],
    plan: PlanArtifacts,
    quality: dict[str, Any],
    scout: dict[str, Any],
    totals: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one run's report record. Evidence text is dropped: it is
    already on disk under the run's scout dir and would bloat the JSON."""
    return {
        "task_key": task["key"],
        "task_label": task["label"],
        "planner_model": totals["planner_model"],
        "plan_policy_applied": totals["plan_policy_applied"],
        "handoff": plan.handoff,
        "plan_path": str(plan.plan_path),
        "plan_error": plan.plan_error,
        "plan_query_count": len(plan.queries),
        "plan_tool_breakdown": plan.tool_breakdown,
        "quality": quality,
        "reposcout": {k: v for k, v in scout.items() if k != "evidence"},
        "repo_leaks": totals["repo_leaks"],
        "totals": totals,
    }
