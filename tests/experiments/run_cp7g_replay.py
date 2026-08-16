"""CP7-G: Result Contract Robustness — replay CP7-F evidence through v2.

CP7-F's change_scope answer reached the consumer in both the Plan and the
Evidence but scored 0.833 because it never wrote the consumer's class name.
That is a failure of the output contract, so CP7-G changes only the output
contract and the evaluator, and holds everything upstream fixed by replaying
CP7-F's stored artifacts rather than regenerating them:

    stored Plan + stored Evidence -> Main Final v2   (exactly one model call)

No Plan generation, no RepoScout run, no Sonnet planner, no A baseline. The
Evidence body is hashed before the call so the replay can be shown to have
used the same bytes CP7-F used. CP7-F's own recorded result is left as-is:
v1 scored it 0.833 under the rules in force at the time, and this script
writes a separate report rather than re-scoring that file.
"""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_metrics import run_claude
from cp7_metrics import parse_plan_queries
from cp7_tasks import TASKS
from cp7g_evaluator import evaluate, evidence_sha256
from prompts import MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_V2
from run_comparison import (
    MAIN_MODEL,
    NO_TOOLS_DISALLOWED,
    categorize_plan_paths,
    count_repo_leaks,
    list_repository_files,
)

TASK_KEY = "change_scope"


def find_source_run(results_root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    candidates = sorted(results_root.glob("*-cp7f"))
    if not candidates:
        raise FileNotFoundError(f"no *-cp7f run directory under {results_root}")
    return candidates[-1]


def load_source(source_run: Path, task_key: str) -> dict[str, Any]:
    """Pull the stored handoff, Plan, Evidence, and recorded metrics."""
    report = json.loads((source_run / "cp7f-results.json").read_text(encoding="utf-8"))
    matching = [r for r in report["results"] if r["task_key"] == task_key]
    if not matching:
        raise KeyError(f"{task_key!r} not present in {source_run / 'cp7f-results.json'}")

    stored = matching[0]
    evidence_path = Path(stored["reposcout"]["evidence_path"])
    return {
        "handoff": stored["handoff"],
        "plan_path": Path(stored["plan_path"]),
        "evidence_path": evidence_path,
        "evidence": evidence_path.read_text(encoding="utf-8"),
        "recorded_evidence_chars": stored["totals"]["evidence_chars"],
        "snapshot": Path(report["snapshot"]),
        "source_totals": stored["totals"],
    }


def verify_evidence(source: dict[str, Any]) -> dict[str, Any]:
    """Prove the replay's Evidence is CP7-F's Evidence.

    CP7-F stored a character count, not a hash, so the count is the invariant
    that can actually be checked against the past; the sha256 recorded here
    becomes the checkable invariant for any later replay.
    """
    evidence: str = source["evidence"]
    return {
        "evidence_sha256": evidence_sha256(source["evidence_path"]),
        "evidence_body_sha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
        "evidence_chars": len(evidence),
        "recorded_evidence_chars": source["recorded_evidence_chars"],
        "evidence_chars_match": len(evidence) == source["recorded_evidence_chars"],
    }


def replay_final_answer(
    task: dict[str, Any], source: dict[str, Any], run_dir: Path
) -> tuple[Any, str]:
    confirmation_points = "\n".join(f"- {point}" for point in task["confirmation_points"])
    transcript = run_dir / f"CP7G-{task['key']}-main-final-v2.jsonl"
    run = run_claude(
        MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_V2.format(
            confirmation_points=confirmation_points,
            handoff=source["handoff"],
            evidence=source["evidence"],
        ),
        label=f"CP7G-{task['key']}-main-final-v2",
        root=source["snapshot"],
        transcript_path=transcript,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (run_dir / f"CP7G-{task['key']}-answer-v2.md").write_text(run.final_text, encoding="utf-8")
    return run, str(transcript)


def build_report(
    task: dict[str, Any],
    source: dict[str, Any],
    integrity: dict[str, Any],
    scores: dict[str, Any],
    run: Any,
    paths: dict[str, Any],
    repo_leaks: int,
) -> dict[str, Any]:
    return {
        "variant": "cp7g",
        "phase": "cp7g-result-contract-robustness",
        "task_key": task["key"],
        "main_model": MAIN_MODEL,
        "replayed_from": str(source["plan_path"].parent),
        "plan_path": str(source["plan_path"]),
        "evidence_path": str(source["evidence_path"]),
        "integrity": integrity,
        "scores": scores,
        "main_final_v2": {
            "input_tokens": run.total_input_tokens,
            "output_tokens": run.output_tokens,
            "cost_usd": round(run.cost_usd, 6),
            "elapsed_seconds": round(run.wall_seconds, 3),
        },
        "nonexistent_path_count": paths["nonexistent_path_count"],
        "nonexistent_paths": paths["nonexistent_paths"],
        "out_of_scope_path_count": paths["out_of_scope_path_count"],
        "out_of_scope_paths": paths["out_of_scope_paths"],
        "repo_leaks": repo_leaks,
        "source_v1_coverage": source["source_totals"]["coverage"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-run", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    results_root = repo_root / "tests/experiments/results"
    source_run = find_source_run(results_root, args.source_run)
    task = next(t for t in TASKS if t["key"] == TASK_KEY)

    source = load_source(source_run, TASK_KEY)
    integrity = verify_evidence(source)
    print(f"Replaying: {source_run}")
    print(f"  evidence sha256      : {integrity['evidence_sha256']}")
    print(
        f"  evidence chars       : {integrity['evidence_chars']} "
        f"(CP7-F recorded {integrity['recorded_evidence_chars']}, "
        f"match={integrity['evidence_chars_match']})"
    )
    if not integrity["evidence_chars_match"]:
        raise SystemExit("evidence body differs from the CP7-F record; aborting replay")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or results_root / f"{timestamp}-cp7g"
    run_dir.mkdir(parents=True, exist_ok=True)

    run, transcript = replay_final_answer(task, source, run_dir)
    scores = evaluate(run.final_text, source["evidence"], task)

    queries, _, _ = parse_plan_queries(source["plan_path"].read_text(encoding="utf-8"))
    paths = categorize_plan_paths(
        queries, list_repository_files(source["snapshot"]), source["snapshot"]
    )
    repo_leaks = count_repo_leaks(Path(transcript), repo_root)

    report = build_report(task, source, integrity, scores, run, paths, repo_leaks)
    (run_dir / "cp7g-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"  evidence_coverage          : {scores['evidence_coverage']}\n"
        f"  structured_answer_coverage : {scores['structured_answer_coverage']}\n"
        f"  legacy_lexical_coverage    : {scores['legacy_lexical_coverage']}\n"
        f"  contract_satisfied         : {scores['contract_satisfied']} "
        f"(missing: {scores['sections_missing']})\n"
        f"  nonexistent_path={report['nonexistent_path_count']} "
        f"out_of_scope_path={report['out_of_scope_path_count']} "
        f"repo_leaks={repo_leaks}\n"
        f"  main_final_v2 in/out={run.total_input_tokens}/{run.output_tokens} "
        f"cost={round(run.cost_usd, 6)} elapsed={round(run.wall_seconds, 3)}s"
    )
    print(f"\nJSON: {run_dir / 'cp7g-results.json'}")

    passed = (
        integrity["evidence_chars_match"]
        and scores["evidence_coverage"] == 1.0
        and scores["structured_answer_coverage"] >= 0.98
        and report["nonexistent_path_count"] == 0
        and repo_leaks == 0
    )
    print(f"all-pass: {passed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
