"""CP7-H: Compact Structured Result Contract — replay through v3.

CP7-G fixed CP7-F's wording-sensitivity failure (FACTS / RELATIONS / SOURCE
LOCATIONS / UNKNOWN / SUMMARY) but paid for it in output: the same fact
about QueryRunner's construction site was written under three different
headings. CP7-H tests whether collapsing the three canonical sections into
one CLAIMS section (subject/predicate/object/source per claim, written once)
holds structured coverage while cutting output.

This script chains through CP7-G's own recorded artifacts rather than
CP7-F's directly, so the Evidence-identity check compares against a sha256
that was itself verified once already, read out of cp7g-results.json rather
than re-typed:

    CP7-G report -> (replayed_from) -> CP7-F report -> stored handoff/plan/evidence
                                                              |
                                                              v
                                                  Opus Main Final v3 (1 call)
                                                              |
                                                              v
                                                   CLAIMS / UNKNOWN / SUMMARY
                                                              |
                                                              v
                                                          evaluator v3

No Plan generation, no RepoScout run, no planner call, no baseline. The Main
Final call always requests MAIN_MODEL (Opus) explicitly via run_claude's
--model flag, independent of whatever model is running this Claude Code
session -- the two are unrelated processes.
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
from cp7h_evaluator import evaluate
from prompts import MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_V3
from run_comparison import (
    MAIN_MODEL,
    NO_TOOLS_DISALLOWED,
    categorize_plan_paths,
    count_repo_leaks,
    list_repository_files,
)

TASK_KEY = "change_scope"


def find_source_run(results_root: Path, glob: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    candidates = sorted(results_root.glob(glob))
    if not candidates:
        raise FileNotFoundError(f"no {glob!r} run directory under {results_root}")
    return candidates[-1]


def load_cp7g_record(cp7g_run: Path) -> dict[str, Any]:
    report = json.loads((cp7g_run / "cp7g-results.json").read_text(encoding="utf-8"))
    return {
        "recorded_evidence_sha256": report["integrity"]["evidence_sha256"],
        "cp7f_run": Path(report["replayed_from"]),
        "plan_path": Path(report["plan_path"]),
        "evidence_path": Path(report["evidence_path"]),
        "main_final_v2_output_tokens": report["main_final_v2"]["output_tokens"],
        "main_final_v2_cost_usd": report["main_final_v2"]["cost_usd"],
        "structured_answer_coverage_v2": report["scores"]["structured_answer_coverage"],
    }


def load_cp7f_record(cp7f_run: Path, task_key: str) -> dict[str, Any]:
    report = json.loads((cp7f_run / "cp7f-results.json").read_text(encoding="utf-8"))
    matching = [r for r in report["results"] if r["task_key"] == task_key]
    if not matching:
        raise KeyError(f"{task_key!r} not present in {cp7f_run / 'cp7f-results.json'}")
    stored = matching[0]
    return {
        "handoff": stored["handoff"],
        "snapshot": Path(report["snapshot"]),
        "recorded_evidence_chars": stored["totals"]["evidence_chars"],
    }


def verify_evidence(
    evidence_path: Path, cp7g_record: dict[str, Any], cp7f_record: dict[str, Any]
) -> dict[str, Any]:
    """Confirm the replay reads the exact bytes CP7-F wrote and CP7-G hashed.

    Both comparison values are read out of prior results files, not typed
    into this script, so a stale copy-paste can't silently pass.
    """
    body = evidence_path.read_text(encoding="utf-8")
    current_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return {
        "evidence_sha256": current_sha256,
        "recorded_evidence_sha256": cp7g_record["recorded_evidence_sha256"],
        "sha256_match": current_sha256 == cp7g_record["recorded_evidence_sha256"],
        "evidence_chars": len(body),
        "recorded_evidence_chars": cp7f_record["recorded_evidence_chars"],
        "evidence_chars_match": len(body) == cp7f_record["recorded_evidence_chars"],
        "evidence": body,
    }


def replay_final_answer(
    task: dict[str, Any], handoff: str, evidence: str, snapshot: Path, run_dir: Path
) -> tuple[Any, str]:
    confirmation_points = "\n".join(f"- {point}" for point in task["confirmation_points"])
    transcript = run_dir / f"CP7H-{task['key']}-main-final-v3.jsonl"
    run = run_claude(
        MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_V3.format(
            confirmation_points=confirmation_points, handoff=handoff, evidence=evidence
        ),
        label=f"CP7H-{task['key']}-main-final-v3",
        root=snapshot,
        transcript_path=transcript,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (run_dir / f"CP7H-{task['key']}-answer-v3.md").write_text(run.final_text, encoding="utf-8")
    return run, str(transcript)


def build_report(
    task: dict[str, Any],
    cp7g_run: Path,
    cp7g_record: dict[str, Any],
    integrity: dict[str, Any],
    scores: dict[str, Any],
    run: Any,
    paths: dict[str, Any],
    repo_leaks: int,
) -> dict[str, Any]:
    output_reduction_pct = round(
        100 * (1 - run.output_tokens / cp7g_record["main_final_v2_output_tokens"]), 1
    )
    cost_reduction_pct = round(100 * (1 - run.cost_usd / cp7g_record["main_final_v2_cost_usd"]), 1)
    return {
        "variant": "cp7h",
        "phase": "cp7h-compact-structured-result-contract",
        "task_key": task["key"],
        "main_model": MAIN_MODEL,
        "replayed_from_cp7g": str(cp7g_run),
        "integrity": {k: v for k, v in integrity.items() if k != "evidence"},
        "scores": scores,
        "main_final_v3": {
            "input_tokens": run.total_input_tokens,
            "output_tokens": run.output_tokens,
            "cost_usd": round(run.cost_usd, 6),
            "elapsed_seconds": round(run.wall_seconds, 3),
        },
        "vs_cp7g_v2": {
            "output_tokens_v2": cp7g_record["main_final_v2_output_tokens"],
            "output_tokens_v3": run.output_tokens,
            "output_tokens_reduction_pct": output_reduction_pct,
            "cost_usd_v2": cp7g_record["main_final_v2_cost_usd"],
            "cost_usd_v3": round(run.cost_usd, 6),
            "cost_reduction_pct": cost_reduction_pct,
        },
        "nonexistent_path_count": paths["nonexistent_path_count"],
        "nonexistent_paths": paths["nonexistent_paths"],
        "out_of_scope_path_count": paths["out_of_scope_path_count"],
        "out_of_scope_paths": paths["out_of_scope_paths"],
        "repo_leaks": repo_leaks,
    }


def evaluate_pass(
    integrity: dict[str, Any], scores: dict[str, Any], report: dict[str, Any]
) -> bool:
    required = (
        integrity["sha256_match"]
        and integrity["evidence_chars_match"]
        and scores["evidence_coverage"] == 1.0
        and scores["compact_structured_coverage"] >= 0.98
        and report["nonexistent_path_count"] == 0
        and report["repo_leaks"] == 0
        and scores["contract_satisfied"]
    )
    roi = (
        report["vs_cp7g_v2"]["output_tokens_v3"] < report["vs_cp7g_v2"]["output_tokens_v2"] * 0.5
        and report["vs_cp7g_v2"]["cost_usd_v3"] < report["vs_cp7g_v2"]["cost_usd_v2"]
    )
    report["required_conditions_met"] = required
    report["roi_conditions_met"] = roi
    return required and roi


def print_integrity(cp7g_run: Path, cp7g_record: dict[str, Any], integrity: dict[str, Any]) -> None:
    print(f"Replaying from CP7-G: {cp7g_run}")
    print(f"  (chained via CP7-F: {cp7g_record['cp7f_run']})")
    print(f"  evidence sha256 (recorded in CP7-G) : {integrity['recorded_evidence_sha256']}")
    print(f"  evidence sha256 (this replay)        : {integrity['evidence_sha256']}")
    print(f"  sha256_match={integrity['sha256_match']}")
    print(
        f"  evidence chars={integrity['evidence_chars']} "
        f"(CP7-F recorded {integrity['recorded_evidence_chars']}, "
        f"match={integrity['evidence_chars_match']})"
    )


def print_summary(
    scores: dict[str, Any], report: dict[str, Any], run: Any, run_dir: Path, passed: bool
) -> None:
    print(
        f"\n  evidence_coverage              : {scores['evidence_coverage']}\n"
        f"  compact_structured_coverage    : {scores['compact_structured_coverage']}\n"
        f"  legacy_lexical_coverage        : {scores['legacy_lexical_coverage']}\n"
        f"  contract_satisfied             : {scores['contract_satisfied']} "
        f"(missing: {scores['sections_missing']})\n"
        f"  claims_total={scores['claims_total']} claims_duplicate={scores['claims_duplicate']} "
        f"summary_chars={scores['summary_chars']} within_limit={scores['summary_within_limit']}\n"
        f"  nonexistent_path={report['nonexistent_path_count']} "
        f"out_of_scope_path={report['out_of_scope_path_count']} repo_leaks={report['repo_leaks']}\n"
        f"  main_final_v3 in/out={run.total_input_tokens}/{run.output_tokens} "
        f"cost={round(run.cost_usd, 6)} elapsed={round(run.wall_seconds, 3)}s\n"
        f"  vs CP7-G v2: output_tokens {report['vs_cp7g_v2']['output_tokens_v2']} -> "
        f"{report['vs_cp7g_v2']['output_tokens_v3']} "
        f"({report['vs_cp7g_v2']['output_tokens_reduction_pct']}% reduction), "
        f"cost {report['vs_cp7g_v2']['cost_usd_v2']} -> {report['vs_cp7g_v2']['cost_usd_v3']} "
        f"({report['vs_cp7g_v2']['cost_reduction_pct']}% reduction)"
    )
    print(f"\nJSON: {run_dir / 'cp7h-results.json'}")
    print(
        f"required_conditions_met={report['required_conditions_met']} "
        f"roi_conditions_met={report['roi_conditions_met']}"
    )
    print(f"all-pass: {passed}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-run", type=Path, default=None, help="a *-cp7g run directory")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    results_root = repo_root / "tests/experiments/results"
    cp7g_run = find_source_run(results_root, "*-cp7g", args.source_run)
    task = next(t for t in TASKS if t["key"] == TASK_KEY)

    cp7g_record = load_cp7g_record(cp7g_run)
    cp7f_record = load_cp7f_record(cp7g_record["cp7f_run"], TASK_KEY)
    integrity = verify_evidence(cp7g_record["evidence_path"], cp7g_record, cp7f_record)
    print_integrity(cp7g_run, cp7g_record, integrity)
    if not (integrity["sha256_match"] and integrity["evidence_chars_match"]):
        raise SystemExit("evidence identity check failed; aborting before any model call")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or results_root / f"{timestamp}-cp7h"
    run_dir.mkdir(parents=True, exist_ok=True)

    run, transcript = replay_final_answer(
        task, cp7f_record["handoff"], integrity["evidence"], cp7f_record["snapshot"], run_dir
    )
    scores = evaluate(run.final_text, integrity["evidence"], task)

    queries, _, _ = parse_plan_queries(cp7g_record["plan_path"].read_text(encoding="utf-8"))
    paths = categorize_plan_paths(
        queries, list_repository_files(cp7f_record["snapshot"]), cp7f_record["snapshot"]
    )
    repo_leaks = count_repo_leaks(Path(transcript), repo_root)

    report = build_report(task, cp7g_run, cp7g_record, integrity, scores, run, paths, repo_leaks)
    passed = evaluate_pass(integrity, scores, report)

    (run_dir / "cp7h-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print_summary(scores, report, run, run_dir, passed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
