"""CP7-F: Planner Routing.

CP7/CP7-D/CP7-E measured one planner configuration at a time across all
tasks. CP7-F instead picks the planner per task from a fixed rule declared in
cp7_tasks.py:

    symbol impact / reference lookup / behavior localization -> Sonnet Planner
    change scope / impact requiring indirect consumers       -> Main-owned Opus

The routing table is data, not inference: no classifier call sits in the
measured path, and a task's planner is readable from its definition alone.

This module only dispatches. Each route reuses the runner that established
its baseline — run_cp7_task.run_task for the Sonnet planner (B3.2, frozen at
CP6) and run_cp7e_task.run_task for main-owned planning — so a routed run is
directly comparable to that baseline and neither runner is duplicated here.
RepoScout, Repository Files, selective context, the Evidence Contract, and
every task's ground truth are untouched.
"""

import argparse
import json
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import run_cp7_task
import run_cp7e_task
from cp7_tasks import MAIN_OWNED, SONNET_PLANNER, TASKS
from run_comparison import EXPLORER_MODEL, MAIN_MODEL, build_snapshot

RouteRunner = Callable[[dict[str, Any], Path, Path, Path], dict[str, Any]]


def _run_sonnet_planner(
    task: dict[str, Any], snapshot: Path, run_dir: Path, repo_root: Path
) -> dict[str, Any]:
    """B3.2 as frozen at CP6: Main Brief -> Sonnet Plan -> RepoScout -> Main."""
    return run_cp7_task.run_task(
        task,
        snapshot,
        run_dir,
        repo_root,
        iteration=1,
        planner_model=EXPLORER_MODEL,
        apply_plan_policy=True,
    )


def _run_main_owned(
    task: dict[str, Any], snapshot: Path, run_dir: Path, repo_root: Path
) -> dict[str, Any]:
    """CP7-E: Main Brief+Plan -> RepoScout -> Main. No Change-Scope Policy."""
    return run_cp7e_task.run_task(task, snapshot, run_dir, repo_root)


ROUTES: dict[str, RouteRunner] = {
    SONNET_PLANNER: _run_sonnet_planner,
    MAIN_OWNED: _run_main_owned,
}


def resolve_route(task: dict[str, Any]) -> RouteRunner:
    """Look up a task's declared route.

    Raises rather than defaulting: an unrouted task silently falling back to
    one planner would make the routing rule untestable from the results.
    """
    route = task.get("planner_route")
    if route not in ROUTES:
        raise ValueError(
            f"task {task['key']!r} declares planner_route={route!r}; "
            f"expected one of {sorted(ROUTES)}"
        )
    return ROUTES[route]


def print_result(task: dict[str, Any], totals: dict[str, Any]) -> None:
    print(
        f"    route={task['planner_route']} planner={totals['planner_model']}\n"
        f"    coverage={totals['coverage']} "
        f"total_in={totals['total_input_tokens']} out={totals['total_output_tokens']} "
        f"cost={totals['total_cost_usd']} elapsed={totals['elapsed_seconds']}s\n"
        f"    queries={totals['reposcout_query_count']} "
        f"effective_query_rate={totals['effective_query_rate']} "
        f"evidence_chars={totals['evidence_chars']}\n"
        f"    nonexistent_path={totals['nonexistent_path_count']} "
        f"out_of_scope_path={totals['out_of_scope_path_count']} "
        f"repo_leaks={totals['repo_leaks']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=[task["key"] for task in TASKS],
        help="subset of task keys to run (default: all three CP7 tasks)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-cp7f"
    run_dir.mkdir(parents=True, exist_ok=True)

    selected = [task for task in TASKS if task["key"] in args.tasks]
    routes = [resolve_route(task) for task in selected]  # fail before any model call

    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-comparison"
    snapshot = build_snapshot(repo_root, snapshot_root / timestamp / "target")
    print(f"Snapshot: {snapshot}")

    results = []
    for task, route in zip(selected, routes, strict=True):
        print(f"--- {task['key']}: {task['label']} (route={task['planner_route']}) ---")
        result = route(task, snapshot, run_dir, repo_root)
        print_result(task, result["totals"])
        results.append(result)

    report = {
        "variant": "cp7f",
        "phase": "cp7f-planner-routing",
        "main_model": MAIN_MODEL,
        "explorer_model": EXPLORER_MODEL,
        "routing": {task["key"]: task["planner_route"] for task in selected},
        "snapshot": str(snapshot),
        "timestamp": timestamp,
        "results": results,
    }
    json_path = run_dir / "cp7f-results.json"
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
