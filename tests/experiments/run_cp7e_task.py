"""CP7-E: Main-Owned Investigation Planning.

CP7-D established that Plan quality on change-scope tasks tracks the planner
model, not the Investigation Policy wording — but paying for a second Opus
call cost +80% and +77% wall time over the Sonnet planner. CP7-E removes the
planner call entirely instead of upgrading it: Main already holds the task
context that the Brief exists to transfer, so it writes the Brief and the
RepoScout Plan in one call.

    CP7-D:  Main Brief -> Opus Planner -> RepoScout -> Main Final   (3 calls)
    CP7-E:  Main Brief + Plan          -> RepoScout -> Main Final   (2 calls)

Unchanged from CP7-D: task, ground truth, Repository Files content, RepoScout,
selective context, Evidence Contract, and the Main final-analysis prompt. No
Change-Scope Policy is applied. No Sonnet/Explorer planner runs.
"""

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_metrics import run_claude
from cp7_metrics import (
    CallTokens,
    PlanArtifacts,
    StageTokens,
    build_result,
    build_totals,
    parse_plan_queries,
    score_generic,
)
from cp7_tasks import TASKS
from prompts import (
    BRIEF_PLAN_SEPARATOR,
    BRIEF_SECTION_HEADER,
    MAIN_BRIEF_AND_PLAN_PROMPT_TEMPLATE,
    MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_GENERIC,
    REPOSITORY_FILES_PLACEHOLDER,
)
from run_comparison import (
    MAIN_MODEL,
    NO_TOOLS_DISALLOWED,
    build_snapshot,
    categorize_plan_paths,
    count_repo_leaks,
    extract_yaml,
    list_repository_files,
    run_reposcout,
)


def _confirmation_points(task: dict[str, Any]) -> str:
    return "\n".join(f"- {point}" for point in task["confirmation_points"])


def split_brief_and_plan(text: str) -> tuple[str, str]:
    """Split Main's single output into the Brief half and the Plan YAML half.

    Raises when the separator is absent: a silent fallback would let a
    malformed run be scored as if planning had succeeded.
    """
    if BRIEF_PLAN_SEPARATOR not in text:
        raise ValueError(f"{BRIEF_PLAN_SEPARATOR!r} not found in Main's brief+plan output")

    brief_part, _, plan_part = text.partition(BRIEF_PLAN_SEPARATOR)
    brief = brief_part.replace(BRIEF_SECTION_HEADER, "").strip()
    return brief, extract_yaml(plan_part)


def plan_with_main(
    task: dict[str, Any],
    snapshot: Path,
    run_dir: Path,
    repository_files: str,
) -> tuple[Any, PlanArtifacts]:
    """Main's single Brief+Plan call. Returns the call record and artifacts."""
    key = task["key"]
    run = run_claude(
        MAIN_BRIEF_AND_PLAN_PROMPT_TEMPLATE.format(
            investigation_goal=task["investigation_goal"],
            confirmation_points=_confirmation_points(task),
            repository_files=repository_files,
        ),
        label=f"CP7E-{key}-main-brief-plan",
        root=snapshot,
        transcript_path=run_dir / f"CP7E-{key}-main-brief-plan.jsonl",
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (run_dir / f"CP7E-{key}-brief-plan-raw.md").write_text(run.final_text, encoding="utf-8")

    brief_text, plan_text = split_brief_and_plan(run.final_text)
    if REPOSITORY_FILES_PLACEHOLDER in brief_text:
        handoff = brief_text.replace(REPOSITORY_FILES_PLACEHOLDER, repository_files)
    else:
        handoff = f"{brief_text}\n\nREPOSITORY FILES\n{repository_files}"

    plan_path = run_dir / f"CP7E-{key}-plan.yaml"
    plan_path.write_text(plan_text, encoding="utf-8")
    queries, tool_breakdown, plan_error = parse_plan_queries(plan_text)
    return run, PlanArtifacts(handoff, plan_path, queries, tool_breakdown, plan_error)


def analyse_with_main(
    task: dict[str, Any],
    snapshot: Path,
    run_dir: Path,
    handoff: str,
    evidence: str,
) -> Any:
    """Main's final analysis call over raw RepoScout evidence."""
    key = task["key"]
    run = run_claude(
        MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_GENERIC.format(
            confirmation_points=_confirmation_points(task),
            handoff=handoff,
            evidence=evidence,
        ),
        label=f"CP7E-{key}-main-final",
        root=snapshot,
        transcript_path=run_dir / f"CP7E-{key}-main-final.jsonl",
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (run_dir / f"CP7E-{key}-answer.md").write_text(run.final_text, encoding="utf-8")
    return run


def run_task(
    task: dict[str, Any],
    snapshot: Path,
    run_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    key = task["key"]
    repository_files = list_repository_files(snapshot)

    brief_plan_run, plan = plan_with_main(task, snapshot, run_dir, repository_files)
    scout = run_reposcout(
        snapshot=snapshot,
        plan_path=plan.plan_path,
        output_dir=run_dir / f"CP7E-{key}-scout",
        repo_root=repo_root,
    )
    final_run = analyse_with_main(task, snapshot, run_dir, plan.handoff, scout["evidence"])

    repo_leaks = count_repo_leaks(
        run_dir / f"CP7E-{key}-main-brief-plan.jsonl", repo_root
    ) + count_repo_leaks(run_dir / f"CP7E-{key}-main-final.jsonl", repo_root)

    quality = score_generic(final_run.final_text, task)
    tokens = StageTokens(
        first_main=CallTokens(brief_plan_run.total_input_tokens, brief_plan_run.output_tokens),
        final_main=CallTokens(final_run.total_input_tokens, final_run.output_tokens),
        planner=CallTokens(),  # no separate planner call in CP7-E
        cost_usd=brief_plan_run.cost_usd + final_run.cost_usd,
        elapsed_seconds=(
            brief_plan_run.wall_seconds + scout["elapsed_seconds"] + final_run.wall_seconds
        ),
    )
    meta = {
        "planner_model": f"{MAIN_MODEL} (main-owned)",
        "plan_policy_applied": None,
        "query_count": len(plan.queries),
        "repo_leaks": repo_leaks,
    }
    path_categories = categorize_plan_paths(plan.queries, repository_files, snapshot)
    totals = build_totals(quality, scout, path_categories, tokens, meta)
    return build_result(task, plan, quality, scout, totals)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    parser.add_argument("--tasks", nargs="*", default=["change_scope"])
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-cp7e"
    run_dir.mkdir(parents=True, exist_ok=True)

    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-comparison"
    snapshot = build_snapshot(repo_root, snapshot_root / timestamp / "target")
    print(f"Snapshot: {snapshot}")

    results = []
    for task in TASKS:
        if task["key"] not in args.tasks:
            continue
        print(f"--- {task['key']}: {task['label']} (main-owned planning) ---")
        result = run_task(task, snapshot, run_dir, repo_root)
        totals = result["totals"]
        print(
            f"    coverage={totals['coverage']} "
            f"total_in={totals['total_input_tokens']} out={totals['total_output_tokens']} "
            f"cost={totals['total_cost_usd']} elapsed={totals['elapsed_seconds']}s "
            f"queries={totals['reposcout_query_count']} "
            f"effective_query_rate={totals['effective_query_rate']} "
            f"nonexistent_path={totals['nonexistent_path_count']} "
            f"out_of_scope_path={totals['out_of_scope_path_count']} "
            f"repo_leaks={totals['repo_leaks']}"
        )
        results.append(result)

    report = {
        "variant": "cp7e",
        "phase": "cp7e-main-owned-planning",
        "main_model": MAIN_MODEL,
        "planner_model": f"{MAIN_MODEL} (main-owned)",
        "snapshot": str(snapshot),
        "timestamp": timestamp,
        "results": results,
    }
    json_path = run_dir / "cp7e-results.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON: {json_path}")

    all_pass = all(
        r["totals"]["coverage"] >= 0.98
        and r["totals"]["nonexistent_path_count"] == 0
        and r["totals"]["repo_leaks"] == 0
        for r in results
    )
    print(f"all-pass (coverage>=0.98, nonexistent_path=0, leaks=0): {all_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
