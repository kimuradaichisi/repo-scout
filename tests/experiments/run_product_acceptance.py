"""RepoScout 1.0 Final Product Acceptance.

Investigation Contract (goal) -> deterministic RepoScout execution ->
Evidence Contract -> model-free evaluator, for CP7's three existing tasks
(symbol_impact, behavior_localization, change_scope). No model, Ornith, or
subagent call anywhere in this file -- QueryRunner is given a FakeOrnithWorker
so a misrouted query would be caught, not silently executed.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cp7_tasks import TASKS
from product_acceptance_checks import AcceptanceResult, evaluate
from product_acceptance_tasks import TASK_QUERIES

from reposcout.models import EvidenceContract, EvidenceResult, InvestigationPlan, InvestigationQuery
from reposcout.runner import InvestigationRunner, QueryRunner

ACCEPTED_TASK_KEYS = ("symbol_impact", "behavior_localization", "change_scope")


class FakeOrnithWorker:
    """Records calls; a real invocation here would mean a query was routed to
    a semantic explorer, which Product Acceptance must never do."""

    def __init__(self) -> None:
        self.calls: list[InvestigationQuery] = []

    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        self.calls.append(query)
        return EvidenceResult(query_id=query.id, status="ERROR", executor="ornith", error="unused")


def _run_task(
    task: dict[str, Any], root: Path, run_dir: Path, ornith: FakeOrnithWorker
) -> tuple[EvidenceContract, Path]:
    plan = InvestigationPlan(goal=task["investigation_goal"], queries=TASK_QUERIES[task["key"]])
    runner = InvestigationRunner(query_runner=QueryRunner(ornith_worker=ornith))
    task_dir = run_dir / task["key"]
    trace_path = task_dir / "trace.jsonl"

    runner.execute(
        root=root,
        plan=plan,
        run_dir=task_dir,
        investigation_id=f"acceptance-{task['key']}",
        trace_out=trace_path,
    )

    contract = EvidenceContract.model_validate(
        json.loads((task_dir / "evidence-contract.json").read_text(encoding="utf-8"))
    )
    return contract, trace_path


def _trace_investigation_id(trace_path: Path, expected_id: str) -> bool:
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    return all(record["investigation_id"] == expected_id for record in records) and any(
        record["record_type"] == "trace" for record in records
    )


def _report_row(result: AcceptanceResult, trace_ok: bool) -> dict[str, Any]:
    return {
        "task_key": result.task_key,
        "passed": result.passed,
        "coverage": result.coverage["coverage"],
        "missing_files": result.coverage["missing_files"],
        "missing_symbols": result.coverage["missing_symbols"],
        "missing_extended": result.coverage["missing_extended"],
        "traceable_files": result.traceable_files,
        "untraceable_files": result.untraceable_files,
        "fictional_paths": result.fictional_paths,
        "repo_leak_count": result.repo_leak_count,
        "unknown_count": result.unknown_count,
        "unresolved_count": result.unresolved_count,
        "error_count": result.error_count,
        "evidence_chars": result.evidence_chars,
        "source_location_count": result.source_location_count,
        "trace_investigation_id_preserved": trace_ok,
    }


def _run_all_tasks(root: Path, run_dir: Path, ornith: FakeOrnithWorker) -> list[dict[str, Any]]:
    tasks = [task for task in TASKS if task["key"] in ACCEPTED_TASK_KEYS]
    rows = []
    for task in tasks:
        print(f"  -> {task['key']}")
        contract, trace_path = _run_task(task, root, run_dir, ornith)
        result = evaluate(task, contract, root)
        trace_ok = _trace_investigation_id(trace_path, f"acceptance-{task['key']}")
        rows.append(_report_row(result, trace_ok))
        print(f"     coverage={result.coverage['coverage']} passed={result.passed}")
    return rows


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = root / "tests/experiments/results" / f"{stamp}-product-acceptance"
    run_dir.mkdir(parents=True, exist_ok=True)

    ornith = FakeOrnithWorker()
    rows = _run_all_tasks(root, run_dir, ornith)

    payload = {
        "variant": "product-acceptance-1.0",
        "ornith_calls": len(ornith.calls),
        "tasks": rows,
        "all_passed": all(row["passed"] for row in rows),
    }
    out_path = run_dir / "product-acceptance-results.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nJSON: {out_path}")
    print(f"ornith_calls: {len(ornith.calls)}")
    print(f"all_passed: {payload['all_passed']}")
    return 0 if payload["all_passed"] and len(ornith.calls) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
