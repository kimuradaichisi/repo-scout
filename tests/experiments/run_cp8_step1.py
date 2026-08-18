"""CP8 Step 1 — N=1 Config A / Config B comparison over T1/T2/T3.

Six runs, each on its own clean snapshot and its own Claude session: Config A
(Main-Opus-Sole) completes all three tasks before Config B (Main +
Sonnet-Worker) starts on any of them, so Config B's setup cannot be tuned in
reaction to Config A's specific results.

Every run is graded the same way regardless of which config produced it: an
independent, blind Opus grader reads the diff and the fixed acceptance
criteria (cp8_step1_grader.py); test_pass/gate_pass/regression_count come
from the harness's own gate run (cp8_step1_gates.py), never from either
party's self-report. Config B additionally gets the role-adherence and
review-integrity metrics rev.2 asked for (cp8_step1_review.py).

Fixed conditions (CLAUDE.md, the subagent definition, both hooks, ./scout)
are hashed on every run and checked against the locked baseline recorded
right after the Preparation commit; a mismatch stops the run rather than
producing a comparison against drifted infrastructure.
"""

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from cp8_diff import diff_against_fixture_commit
from cp8_fixtures import (
    inject_reposcout_bin,
    isolate_environment,
    read_if_exists,
)
from cp8_packs import extract_pack_paths, split_sections
from cp8_step1_config import CONFIG_A, CONFIG_B, StepConfig
from cp8_step1_gates import run_gates
from cp8_step1_grader import grade_run
from cp8_step1_metrics import (
    active_config_check,
    evaluation_metrics,
    load_run_events,
    main_role_metrics,
    model_usage_breakdown,
    quality_metrics,
    run_call_metrics,
    safety_metrics,
    worker_behavior_metrics,
)
from cp8_step1_prompts import MAIN_REPORT_SECTIONS
from cp8_step1_report import compare_task, evaluate_hard_gates, go_no_go
from cp8_step1_review import delegation_rounds
from cp8_step1_runtime import (
    PRE_WORKER_LOG,
    ROLE_LOG,
    RunPaths,
    check_locked_hashes,
    clear_hook_logs,
    run_main,
    setup_snapshot,
)
from cp8_tasks import TASKS


def _pack_paths(events: list[dict[str, Any]]) -> frozenset[str]:
    paths: frozenset[str] = frozenset()
    for round_ in delegation_rounds(events):
        paths |= extract_pack_paths(round_.pack_text)
    return paths


def _default_main_role() -> dict[str, Any]:
    """Config A's main_role slice: nothing to delegate, nothing to violate."""
    return {
        "main_direct_write_count": 0,
        "pre_worker_diff_empty": None,
        "review_gate_match": None,
        "rework_cycles": 0,
        "unknown_blocked_count": 0,
        "worker_scope_violation_count": 0,
        "delegation_rounds": 0,
    }


def _execute_and_grade(config: StepConfig, task: dict[str, Any], paths: RunPaths) -> dict[str, Any]:
    """Run Main to completion, then gate and grade what it produced."""
    before_gates = run_gates(paths.snapshot)
    clear_hook_logs(paths.snapshot)

    prompt = config.render_prompt(task)
    run, transcript = run_main(prompt, paths.label, config, paths.snapshot, paths.run_dir)
    events = load_run_events(transcript)

    diff_text, changed_paths = diff_against_fixture_commit(paths.snapshot)
    after_gates = run_gates(paths.snapshot)

    main_sections = split_sections(run.final_text, MAIN_REPORT_SECTIONS)
    gate_output = "\n".join(
        main_sections.get(name, "") for name in ("TEST RESULTS", "QUALITY GATE RESULTS")
    )
    grader_transcript = paths.run_dir / f"{paths.label}-grader.jsonl"
    grade = grade_run(task, diff_text, gate_output, paths.snapshot, grader_transcript)

    return {
        "run": run,
        "transcript": transcript,
        "events": events,
        "diff_text": diff_text,
        "changed_paths": changed_paths,
        "before_gates": before_gates,
        "after_gates": after_gates,
        "grade": grade,
    }


def _delegation_slice(
    config: StepConfig, role_log: str, pre_worker_log: str, execution: dict[str, Any]
) -> dict[str, Any]:
    """worker_behavior + main_role, or Config A's flat defaults for the same keys."""
    if not config.is_delegating:
        return {"worker_behavior": None, "main_role": _default_main_role()}

    events = execution["events"]
    return {
        "worker_behavior": worker_behavior_metrics(events, _pack_paths(events)),
        "main_role": main_role_metrics(
            events,
            role_log,
            pre_worker_log,
            execution["changed_paths"],
            execution["after_gates"].gate_pass,
        ),
    }


def _base_report(
    config: StepConfig, task: dict[str, Any], repo_root: Path, run: dict[str, Any]
) -> dict[str, Any]:
    execution = run["execution"]
    return {
        "run_key": run["label"],
        "config": config.key,
        "task_key": task["key"],
        "aborted": False,
        "fixed_condition_hashes": run["hashes"],
        "quality": quality_metrics(
            execution["before_gates"],
            execution["after_gates"],
            execution["changed_paths"],
            task,
            execution["grade"],
        ),
        "evaluation": evaluation_metrics(execution["grade"]),
        "model_usage": model_usage_breakdown(execution["events"]),
        "main_call": run_call_metrics(execution["run"]),
        "safety": safety_metrics(execution["transcript"], repo_root),
        "active_config": active_config_check(run["role_log"], config.key),
        "changed_paths": execution["changed_paths"],
        "diff_chars": len(execution["diff_text"]),
    }


def _assemble_report(
    config: StepConfig,
    task: dict[str, Any],
    paths: RunPaths,
    repo_root: Path,
    hashes: dict[str, Any],
) -> dict[str, Any]:
    execution = _execute_and_grade(config, task, paths)
    role_log = read_if_exists(paths.snapshot / ROLE_LOG)
    pre_worker_log = read_if_exists(paths.snapshot / PRE_WORKER_LOG)

    run = {"execution": execution, "hashes": hashes, "role_log": role_log, "label": paths.label}
    report = _base_report(config, task, repo_root, run)
    report |= _delegation_slice(config, role_log, pre_worker_log, execution)
    report["hard_gates"] = evaluate_hard_gates(report, config.is_delegating)
    return report


def _run_one(
    config: StepConfig, task: dict[str, Any], paths: RunPaths, repo_root: Path
) -> dict[str, Any]:
    hash_check = check_locked_hashes(repo_root, paths.snapshot)
    if not hash_check["matches_locked"]:
        return {
            "run_key": paths.label,
            "config": config.key,
            "task_key": task["key"],
            "fixed_condition_drift": hash_check["drifted"],
            "aborted": True,
        }
    return _assemble_report(
        config, task, paths, repo_root, hash_check["current"]["fixed_condition_hashes"]
    )


def _run_task_for_config(
    config: StepConfig, task: dict[str, Any], repo_root: Path, snapshot_root: Path, run_dir: Path
) -> dict[str, Any]:
    label = f"CP8-step1-{config.key}-{task['key']}"
    dest = snapshot_root / label / "target"
    snapshot = setup_snapshot(repo_root, dest)
    paths = RunPaths(snapshot=snapshot, run_dir=run_dir, label=label)
    print(f"  -> {label}")
    report = _run_one(config, task, paths, repo_root)
    print(f"     hard_gates.all_passed={report.get('hard_gates', {}).get('all_passed')}")
    return report


def _setup(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-cp8-step1"
    run_dir.mkdir(parents=True, exist_ok=True)
    inject_reposcout_bin(repo_root)
    isolate_environment(repo_root, repo_root)
    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-cp8-step1"
    return repo_root, snapshot_root, run_dir


def _run_all_tasks(
    config: StepConfig, repo_root: Path, snapshot_root: Path, run_dir: Path
) -> dict[str, dict[str, Any]]:
    return {
        task["key"]: _run_task_for_config(config, task, repo_root, snapshot_root, run_dir)
        for task in TASKS
    }


def _build_final_report(
    a_reports: dict[str, dict[str, Any]], b_reports: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    comparisons = [
        compare_task(a_reports[task["key"]], b_reports[task["key"]])
        for task in TASKS
        if not a_reports[task["key"]]["aborted"] and not b_reports[task["key"]]["aborted"]
    ]
    decision = go_no_go(comparisons, list(b_reports.values()))
    return {
        "variant": "cp8-step1",
        "phase": "cp8-step1-n1-comparison",
        "config_a": a_reports,
        "config_b": b_reports,
        "comparisons": comparisons,
        "go_no_go": decision,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    repo_root, snapshot_root, run_dir = _setup(parser.parse_args())

    print("=== Config A (Main-Opus-Sole) ===")
    a_reports = _run_all_tasks(CONFIG_A, repo_root, snapshot_root, run_dir)
    print("=== Config B (Main + Sonnet Worker) ===")
    b_reports = _run_all_tasks(CONFIG_B, repo_root, snapshot_root, run_dir)

    report = _build_final_report(a_reports, b_reports)
    (run_dir / "cp8-step1-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nJSON: {run_dir / 'cp8-step1-results.json'}")
    print(f"go_no_go: {report['go_no_go']['go']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
