"""CP9 Step 0 — task family, telemetry and gate validation. No model calls.

Nothing here starts a Claude process. Step 0 exists to prove that the things
Step 0.5 will rely on are already true: that S/M/L differ only in scope, that
the telemetry extractor agrees with real transcripts, that Decision Identity
refuses what it cannot read, and that the Axis Validity Gate fails when it
should. Its output is the record that those thresholds were fixed before any
CP9 run existed to fit them to.
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import cp9_step0_decision_checks as decision_checks
import cp9_step0_task_checks as task_checks
import cp9_step0_telemetry_checks as telemetry_checks
from cp9_axis_gate import registered_thresholds
from cp9_tasks import TASKS


def _report(title: str, results: list[Any]) -> dict[str, Any]:
    print(f"\n--- {title} ---")
    for result in results:
        print(f"  [{'PASS' if result.passed else 'FAIL'}] {result.name}")
        print(f"        {result.detail}")
    return {
        "checks": [asdict(result) for result in results],
        "all_passed": all(result.passed for result in results),
    }


def _task_summary() -> list[dict[str, Any]]:
    return [
        {
            "key": task["key"],
            "size": task["size"],
            "decision_count": task["decision_count"],
            "volume": task["volume"],
            "targets": list(task["targets"]),
            "forbidden_paths": list(task["forbidden_paths"]),
            "outcome_criteria_count": len(task["outcome_criteria"]),
            "contract_criteria_count": len(task["contract_criteria"]),
        }
        for task in TASKS
    ]


def _build_report(repo_root: Path, experiments: Path) -> dict[str, Any]:
    report = {
        "variant": "cp9-step0",
        "tasks": _task_summary(),
        "registered_thresholds": registered_thresholds(),
        "task_definition": _report("Task definition", task_checks.run_all(repo_root)),
        "telemetry": _report(
            "Telemetry extraction",
            telemetry_checks.run_all(experiments / telemetry_checks.CP8_RUN_DIR),
        ),
        "decision_and_gate": _report("Decision Identity / Axis Gate", decision_checks.run_all()),
    }
    report["all_passed"] = all(
        report[name]["all_passed"] for name in ("task_definition", "telemetry", "decision_and_gate")
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    experiments = repo_root / "tests/experiments"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or experiments / "results" / f"{stamp}-cp9-step0"
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=== CP9 Step 0 (no model calls) ===")
    report = _build_report(repo_root, experiments)
    (run_dir / "cp9-step0-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nJSON: {run_dir / 'cp9-step0-results.json'}")
    print(f"all_passed: {report['all_passed']}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
