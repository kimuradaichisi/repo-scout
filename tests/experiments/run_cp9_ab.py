"""CP9-v3 A/B at one size: Config A, then Config B, N=1, independent snapshots.

Config A finishes before Config B starts, on its own clean snapshot and its
own session, so Config B cannot be tuned in reaction to what A happened to do.
Both sides get the identical task text, criteria and report shape; the only
difference is who implements.

Quality is deterministic. Gates, regression and scope are computed by the
harness against the snapshot, so neither party's self-report can move them and
no grader call is needed -- which also means every cost figure here is
execution cost, with nothing to subtract.

Decision Identity is computed between the two configs at the same size and
reported as a diagnostic. It gates nothing: if A and B resolved the design
differently, the cost comparison is between two different implementations, and
a reader needs to see that rather than have it folded into a verdict.
"""

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from cp8_diff import diff_against_fixture_commit
from cp8_fixtures import inject_reposcout_bin, isolate_environment, read_if_exists
from cp8_step1_metrics import model_usage_breakdown, run_call_metrics, safety_metrics
from cp8_step1_review import main_direct_write_count, pre_worker_diff_empty
from cp8_step1_runtime import PRE_WORKER_LOG, ROLE_LOG, clear_hook_logs, setup_snapshot
from cp8_transcript import load_events
from cp9_ab_report import compare, next_step
from cp9_config import CONFIG_A, CONFIG_B, RunConfig
from cp9_decision import PROTOCOL_VERSION, parse_decision_record, record_summary
from cp9_decision import compare as compare_decisions
from cp9_execution_scope import execution_scope
from cp9_gates import gate_summary, regression_report, run_gates
from cp9_runtime import RunPaths, check_locked_hashes, run_main
from cp9_scope import scope_report
from cp9_tasks import get_size
from cp9_telemetry import (
    delegation_records,
    denial_counts,
    main_phase_boundary_tools,
    main_write_calls,
    observed_models,
    phase_totals,
)


def _execute(
    config: RunConfig, task: dict[str, Any], paths: RunPaths, root: Path
) -> dict[str, Any]:
    before = run_gates(paths.snapshot, paths.run_dir / f"{paths.label}-junit-baseline.xml")
    clear_hook_logs(paths.snapshot)
    run, transcript = run_main(config.render_prompt(task), config, paths)
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
        "safety": safety_metrics(transcript, root),
        "role_log": read_if_exists(paths.snapshot / ROLE_LOG),
        "pre_worker_log": read_if_exists(paths.snapshot / PRE_WORKER_LOG),
    }


def _delegation_slice(config: RunConfig, execution: dict[str, Any]) -> dict[str, Any]:
    events = execution["events"]
    records = delegation_records(events)
    return {
        "delegation_rounds": len(records),
        "delegation_records": records,
        "worker_models": sorted({str(r["resolved_model"]) for r in records}),
        "main_write_calls": main_write_calls(events),
        "main_write_denials_from_role_gate": main_direct_write_count(execution["role_log"]),
        "pre_worker_diff_empty": pre_worker_diff_empty(execution["pre_worker_log"]),
        "permission_denials": denial_counts(events),
        "is_delegating": config.is_delegating,
    }


def _measured(execution: dict[str, Any]) -> dict[str, Any]:
    """The harness-computed half: nothing here comes from anyone's self-report."""
    return {
        "quality": execution["quality"],
        "regression": execution["regression"],
        "scope": execution["scope"],
        "changed_paths": execution["changed_paths"],
        "diff_chars": execution["diff_chars"],
        "model_usage": model_usage_breakdown(execution["events"]),
        "main_call": run_call_metrics(execution["run"]),
        "safety": execution["safety"],
        "models_observed": observed_models(execution["events"]),
    }


def _report(
    config: RunConfig, task: dict[str, Any], execution: dict[str, Any], hashes: dict[str, Any]
) -> dict[str, Any]:
    record = parse_decision_record(execution["run"].final_text)
    phases = phase_totals(execution["events"], main_phase_boundary_tools(config.is_delegating))
    return {
        "size": task["size"],
        "task_key": task["key"],
        "config": config.key,
        "aborted": False,
        "protocol_version": PROTOCOL_VERSION,
        "volume": task["volume"],
        "decision_count": task["decision_count"],
        "fixed_condition_hashes": hashes,
        **_measured(execution),
        "decision_record": record_summary(record),
        "execution_scope": execution_scope(task, record),
        "phase_telemetry": phases,
        "delegation": _delegation_slice(config, execution),
        "_record": record,
    }


def _run_one(config: RunConfig, size: str, root: Path, snapshot_root: Path, run_dir: Path) -> dict:
    task = get_size(size)
    label = f"CP9-ab-{config.key}-{task['key']}"
    snapshot = setup_snapshot(root, snapshot_root / label / "target")
    paths = RunPaths(snapshot=snapshot, run_dir=run_dir, label=label)
    print(f"  -> {label}")

    hash_check = check_locked_hashes(root, snapshot)
    if not hash_check["matches_locked"]:
        return {
            "size": size,
            "config": config.key,
            "aborted": True,
            "fixed_condition_drift": hash_check["drifted"],
        }
    report = _report(config, task, _execute(config, task, paths, root), hash_check["current"])
    usage, call = report["model_usage"], report["main_call"]
    print(
        f"     opus={usage['opus']['total_tokens']} sonnet={usage['sonnet']['total_tokens']}"
        f" cost=${call['cost_usd']:.4f} elapsed={call['elapsed_seconds']:.1f}s"
    )
    return report


def _setup(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    root = args.repo_root.resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or root / "tests/experiments/results" / f"{stamp}-cp9-ab-{args.size}"
    run_dir.mkdir(parents=True, exist_ok=True)
    inject_reposcout_bin(root)
    isolate_environment(root, root)
    snapshot_root = (
        args.snapshot_dir or Path(tempfile.gettempdir()) / f"reposcout-cp9-ab-{args.size}"
    )
    return root, snapshot_root, run_dir


def _build_payload(size: str, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    aborted = [key for key, report in reports.items() if report.get("aborted")]
    comparison = None
    if not aborted:
        identity = compare_decisions(reports["config_a"]["_record"], reports["config_b"]["_record"])
        comparison = compare(reports["config_a"], reports["config_b"], identity)
    for report in reports.values():
        report.pop("_record", None)
    return {
        "variant": f"cp9-ab-{size}",
        "protocol_version": PROTOCOL_VERSION,
        "size": size,
        "runs": reports,
        "comparison": comparison,
        "next_step": next_step(comparison) if comparison else None,
        "aborted": aborted,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", required=True, choices=["S", "M", "L"])
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    args = parser.parse_args()
    root, snapshot_root, run_dir = _setup(args)

    print(f"=== CP9-v3 A/B at size {args.size} (N=1) ===")
    reports = {
        config.key: _run_one(config, args.size, root, snapshot_root, run_dir)
        for config in (CONFIG_A, CONFIG_B)
    }
    payload = _build_payload(args.size, reports)
    comparison = payload["comparison"]
    (run_dir / f"cp9-ab-{args.size}-results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nJSON: {run_dir / f'cp9-ab-{args.size}-results.json'}")
    if comparison:
        print(f"reversal: {comparison['reversal']['reversed_metrics'] or 'none'}")
        print(f"next: {payload['next_step']['action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
