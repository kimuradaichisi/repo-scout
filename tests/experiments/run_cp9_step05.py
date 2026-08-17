"""CP9 Step 0.5 — does the execution-volume axis actually move? Config A only.

Two runs, S and L, both Main-Opus-Sole. Nothing here compares configs: the
question is narrower and comes first. If Config A's own consumption does not
grow with the size of the task, then S and L are not two points on a volume
axis and every A/B number Step 1 would produce would be plotted against
nothing.

Config B is not run. M is not run. The gate thresholds were fixed in
cp9_axis_gate.py before this file existed, and a FAIL stops CP9 rather than
prompting a resize: retuning the sizes until the axis validates would be
choosing the task family that gives the wanted answer.
"""

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from cp8_diff import diff_against_fixture_commit
from cp8_fixtures import inject_reposcout_bin, isolate_environment
from cp8_step1_metrics import model_usage_breakdown, run_call_metrics, safety_metrics
from cp8_step1_runtime import clear_hook_logs, setup_snapshot
from cp8_transcript import load_events
from cp9_axis_gate import (
    check_decision_count,
    check_decision_identity,
    check_decision_phase_calls,
    check_decision_phase_tokens,
    check_opus_growth,
    evaluate,
    registered_thresholds,
)
from cp9_config import CONFIG_A
from cp9_decision import compare, parse_decision_record, record_summary
from cp9_gates import gate_summary, regression_report, run_gates
from cp9_runtime import RunPaths, check_locked_hashes, run_main
from cp9_scope import scope_report
from cp9_tasks import get_size
from cp9_telemetry import (
    DECISION_PHASE,
    IMPLEMENTATION_PHASE,
    delegation_records,
    denial_counts,
    main_phase_boundary_tools,
    observed_models,
    phase_totals,
)

SIZES = ("S", "L")


def _execute(task: dict[str, Any], paths: RunPaths, repo_root: Path) -> dict[str, Any]:
    """Baseline gates, the run, then post-change gates. JUnit XML stays out of the snapshot."""
    before = run_gates(paths.snapshot, paths.run_dir / f"{paths.label}-junit-baseline.xml")
    clear_hook_logs(paths.snapshot)
    run, transcript = run_main(CONFIG_A.render_prompt(task), CONFIG_A, paths)
    events = load_events(transcript)
    diff_text, changed_paths = diff_against_fixture_commit(paths.snapshot)
    after = run_gates(paths.snapshot, paths.run_dir / f"{paths.label}-junit-post.xml")
    return {
        "run": run,
        "events": events,
        "transcript": transcript,
        "changed_paths": changed_paths,
        "diff_chars": len(diff_text),
        "quality": gate_summary(after),
        "regression": regression_report(before.outcomes, after.outcomes),
        "scope": scope_report(changed_paths, task),
        "safety": safety_metrics(transcript, repo_root),
    }


def _decision_slice(execution: dict[str, Any]) -> dict[str, Any]:
    record = parse_decision_record(execution["run"].final_text)
    phases = phase_totals(execution["events"], main_phase_boundary_tools(False))
    return {
        "decision_record": record_summary(record),
        "phase_telemetry": phases,
        "_record": record,
        "_decision": phases[DECISION_PHASE],
        "_implementation": phases[IMPLEMENTATION_PHASE],
    }


def _report(
    task: dict[str, Any], execution: dict[str, Any], hashes: dict[str, Any]
) -> dict[str, Any]:
    decision = _decision_slice(execution)
    usage = model_usage_breakdown(execution["events"])
    return {
        "size": task["size"],
        "task_key": task["key"],
        "config": CONFIG_A.key,
        "aborted": False,
        "volume": task["volume"],
        "decision_count": task["decision_count"],
        "fixed_condition_hashes": hashes,
        "quality": execution["quality"],
        "regression": execution["regression"],
        "scope": execution["scope"],
        "changed_paths": execution["changed_paths"],
        "diff_chars": execution["diff_chars"],
        "model_usage": usage,
        "main_call": run_call_metrics(execution["run"]),
        "safety": execution["safety"],
        "models_observed": observed_models(execution["events"]),
        "delegation_records": delegation_records(execution["events"]),
        "permission_denials": denial_counts(execution["events"]),
        "decision_record": decision["decision_record"],
        "phase_telemetry": decision["phase_telemetry"],
        "_internal": decision,
    }


def _run_one(size: str, repo_root: Path, snapshot_root: Path, run_dir: Path) -> dict[str, Any]:
    task = get_size(size)
    label = f"CP9-step05-config_a-{task['key']}"
    snapshot = setup_snapshot(repo_root, snapshot_root / label / "target")
    paths = RunPaths(snapshot=snapshot, run_dir=run_dir, label=label)
    print(f"  -> {label}")

    hash_check = check_locked_hashes(repo_root, snapshot)
    if not hash_check["matches_locked"]:
        return {
            "size": size,
            "task_key": task["key"],
            "aborted": True,
            "fixed_condition_drift": hash_check["drifted"],
        }

    report = _report(task, _execute(task, paths, repo_root), hash_check["current"])
    print(f"     opus_tokens={report['model_usage']['opus']['total_tokens']}")
    return report


def _axis_gate(small: dict[str, Any], large: dict[str, Any]) -> dict[str, Any]:
    identity = compare(small["_internal"]["_record"], large["_internal"]["_record"])
    small_dp, large_dp = small["_internal"]["_decision"], large["_internal"]["_decision"]
    checks = [
        check_opus_growth(
            small["model_usage"]["opus"]["total_tokens"],
            large["model_usage"]["opus"]["total_tokens"],
        ),
        check_decision_count(small["decision_count"], large["decision_count"]),
        check_decision_identity(identity),
        check_decision_phase_tokens(small_dp["input_cache_tokens"], large_dp["input_cache_tokens"]),
        check_decision_phase_calls(small_dp["tool_calls"], large_dp["tool_calls"]),
    ]
    elapsed = _elapsed_ratio(small_dp, large_dp)
    return evaluate(checks, elapsed) | {"decision_identity": identity}


def _elapsed_ratio(small: dict[str, Any], large: dict[str, Any]) -> float | None:
    small_value, large_value = small.get("elapsed_seconds"), large.get("elapsed_seconds")
    if not small_value or not large_value:
        return None
    return round(large_value / small_value, 4)


def _setup(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    repo_root = args.repo_root.resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{stamp}-cp9-step05"
    run_dir.mkdir(parents=True, exist_ok=True)
    inject_reposcout_bin(repo_root)
    isolate_environment(repo_root, repo_root)
    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-cp9-step05"
    return repo_root, snapshot_root, run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    repo_root, snapshot_root, run_dir = _setup(parser.parse_args())

    print("=== CP9 Step 0.5 — Config A only, S and L ===")
    reports = {size: _run_one(size, repo_root, snapshot_root, run_dir) for size in SIZES}
    aborted = [size for size, report in reports.items() if report.get("aborted")]
    gate = None if aborted else _axis_gate(reports["S"], reports["L"])
    for report in reports.values():
        report.pop("_internal", None)

    payload = {
        "variant": "cp9-step05",
        "phase": "axis-validity",
        "registered_thresholds": registered_thresholds(),
        "runs": reports,
        "axis_validity_gate": gate,
        "aborted_sizes": aborted,
    }
    (run_dir / "cp9-step05-results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nJSON: {run_dir / 'cp9-step05-results.json'}")
    print(f"axis_valid: {gate['axis_valid'] if gate else 'ABORTED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
