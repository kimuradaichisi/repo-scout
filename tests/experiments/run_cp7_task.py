"""CP7: Task Generalization.

Runs the B3.2 architecture (candidate-v1, frozen at CP6) fresh against one of
three investigation tasks whose subsystem, required evidence, and coverage
ground truth are fixed in cp7_tasks.py BEFORE this script is run. Nothing in
B3.2's prompts, RepoScout query handling, or the selective-context threshold
is touched here — only the investigation target changes:

    Main(Opus) Brief -> Explorer(Sonnet) Plan -> RepoScout(selective context)
    -> Main(Opus) final

No synthesis stage. This does not re-run A/B1/B2/B3/B3.1/B3.2-InvestigationRunner.
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
    CHANGE_SCOPE_POLICY,
    EXPLORER_PLAN_PROMPT_TEMPLATE,
    MAIN_BRIEF_PROMPT_TEMPLATE,
    MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_GENERIC,
    REPOSITORY_FILES_PLACEHOLDER,
)
from run_comparison import (
    EXPLORER_MODEL,
    MAIN_MODEL,
    NO_TOOLS_DISALLOWED,
    build_snapshot,
    categorize_plan_paths,
    count_repo_leaks,
    extract_yaml,
    list_repository_files,
    run_reposcout,
)

PLAN_POLICIES = {
    "change_scope": CHANGE_SCOPE_POLICY,
}


def run_task(
    task: dict[str, Any],
    snapshot: Path,
    run_dir: Path,
    repo_root: Path,
    iteration: int,
    planner_model: str = EXPLORER_MODEL,
    apply_plan_policy: bool = True,
) -> dict[str, Any]:
    key = task["key"]
    confirmation_points = "\n".join(f"- {point}" for point in task["confirmation_points"])
    repository_files = list_repository_files(snapshot)

    brief_prompt = MAIN_BRIEF_PROMPT_TEMPLATE.format(
        investigation_goal=task["investigation_goal"],
        confirmation_points=confirmation_points,
    )
    brief_run = run_claude(
        brief_prompt,
        label=f"CP7-{key}-main-brief-{iteration}",
        root=snapshot,
        transcript_path=run_dir / f"CP7-{key}-{iteration}-main-brief.jsonl",
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    brief_text = brief_run.final_text.strip()
    if REPOSITORY_FILES_PLACEHOLDER in brief_text:
        handoff = brief_text.replace(REPOSITORY_FILES_PLACEHOLDER, repository_files)
    else:
        handoff = f"{brief_text}\n\nREPOSITORY FILES\n{repository_files}"

    explorer_plan_prompt = EXPLORER_PLAN_PROMPT_TEMPLATE.format(handoff=handoff)
    policy_key = task.get("plan_policy") if apply_plan_policy else None
    if policy_key:
        explorer_plan_prompt = f"{explorer_plan_prompt}\n{PLAN_POLICIES[policy_key]}"

    explorer_plan_transcript = run_dir / f"CP7-{key}-{iteration}-explorer-plan.jsonl"
    explorer_plan_run = run_claude(
        explorer_plan_prompt,
        label=f"CP7-{key}-explorer-plan-{iteration}",
        root=snapshot,
        transcript_path=explorer_plan_transcript,
        model=planner_model,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )

    plan_text = extract_yaml(explorer_plan_run.final_text)
    plan_path = run_dir / f"CP7-{key}-{iteration}-plan.yaml"
    plan_path.write_text(plan_text, encoding="utf-8")

    queries, tool_breakdown, plan_error = parse_plan_queries(plan_text)
    query_count = len(queries)
    path_categories = categorize_plan_paths(queries, repository_files, snapshot)

    scout = run_reposcout(
        snapshot=snapshot,
        plan_path=plan_path,
        output_dir=run_dir / f"CP7-{key}-{iteration}-scout",
        repo_root=repo_root,
    )

    main_final_transcript = run_dir / f"CP7-{key}-{iteration}-main-final.jsonl"
    main_final_prompt = MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_GENERIC.format(
        confirmation_points=confirmation_points, handoff=handoff, evidence=scout["evidence"]
    )
    main_final_run = run_claude(
        main_final_prompt,
        label=f"CP7-{key}-main-final-{iteration}",
        root=snapshot,
        transcript_path=main_final_transcript,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (run_dir / f"CP7-{key}-{iteration}-answer.md").write_text(
        main_final_run.final_text, encoding="utf-8"
    )

    repo_leaks = count_repo_leaks(explorer_plan_transcript, repo_root) + count_repo_leaks(
        main_final_transcript, repo_root
    )

    quality = score_generic(main_final_run.final_text, task)
    tokens = StageTokens(
        first_main=CallTokens(brief_run.total_input_tokens, brief_run.output_tokens),
        final_main=CallTokens(main_final_run.total_input_tokens, main_final_run.output_tokens),
        planner=CallTokens(explorer_plan_run.total_input_tokens, explorer_plan_run.output_tokens),
        cost_usd=brief_run.cost_usd + explorer_plan_run.cost_usd + main_final_run.cost_usd,
        elapsed_seconds=(
            brief_run.wall_seconds
            + explorer_plan_run.wall_seconds
            + scout["elapsed_seconds"]
            + main_final_run.wall_seconds
        ),
    )
    meta = {
        "planner_model": planner_model,
        "plan_policy_applied": policy_key or None,
        "query_count": query_count,
        "repo_leaks": repo_leaks,
    }

    plan = PlanArtifacts(handoff, plan_path, queries, tool_breakdown, plan_error)
    totals = build_totals(quality, scout, path_categories, tokens, meta)
    return build_result(task, plan, quality, scout, totals)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=[task["key"] for task in TASKS],
        help="subset of task keys to run (default: all)",
    )
    parser.add_argument(
        "--planner-model",
        default=EXPLORER_MODEL,
        help="model used for Explorer Plan generation only (CP7-D swaps this to Opus)",
    )
    parser.add_argument(
        "--no-plan-policy",
        action="store_true",
        help="skip the per-task plan_policy injection (restores the CP7 prompt exactly)",
    )
    parser.add_argument("--phase", default="cp7-task-generalization")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-cp7"
    run_dir.mkdir(parents=True, exist_ok=True)

    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-comparison"
    snapshot = build_snapshot(repo_root, snapshot_root / timestamp / "target")
    print(f"Snapshot: {snapshot}")

    results = []
    for task in TASKS:
        if task["key"] not in args.tasks:
            continue
        print(f"--- {task['key']}: {task['label']} (planner={args.planner_model}) ---")
        result = run_task(
            task,
            snapshot,
            run_dir,
            repo_root,
            iteration=1,
            planner_model=args.planner_model,
            apply_plan_policy=not args.no_plan_policy,
        )
        totals = result["totals"]
        print(
            f"    coverage={totals['coverage']} "
            f"plan_policy={totals['plan_policy_applied']} "
            f"total_in={totals['total_input_tokens']} out={totals['total_output_tokens']} "
            f"cost={totals['total_cost_usd']} elapsed={totals['elapsed_seconds']}s "
            f"effective_query_rate={totals['effective_query_rate']} "
            f"nonexistent_path={totals['nonexistent_path_count']} "
            f"out_of_scope_path={totals['out_of_scope_path_count']} "
            f"target_enclosing_consumer_evidence="
            f"{totals['target_enclosing_consumer_evidence_present']} "
            f"repo_leaks={totals['repo_leaks']}"
        )
        results.append(result)

    report = {
        "variant": "b3.2",
        "phase": args.phase,
        "main_model": MAIN_MODEL,
        "explorer_model": EXPLORER_MODEL,
        "planner_model": args.planner_model,
        "plan_policy_disabled": args.no_plan_policy,
        "snapshot": str(snapshot),
        "timestamp": timestamp,
        "results": results,
    }
    json_path = run_dir / "cp7-results.json"
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
