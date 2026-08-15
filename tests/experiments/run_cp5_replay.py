"""CP5: Evidence Robustness — bounded rg context, same fixed Plan.

Hypothesis: treating an rg match as a locator rather than the evidence itself,
and deterministically attaching bounded source context around it (now done in
RipgrepExecutor.CONTEXT_LINES), reduces Evidence gaps without any extra LLM
round-trip.

This script does NOT generate a new Explorer Plan and does NOT touch A/B1/B2/
B3/B3.1. It reuses the exact plan.yaml that produced B3.1's coverage=0.8 run,
re-executes RepoScout against the same snapshot (now with bounded rg context),
and feeds the new raw evidence straight to Main(Opus) final analysis — the
same "no synthesis" structure as B3.1:

    B3.1 (already run): same Plan -> RepoScout (rg match-line only) -> Main final  -> coverage 0.8
    CP5  (this script):  same Plan -> RepoScout (rg + bounded context) -> Main final -> coverage ?
"""

import argparse
import json
from pathlib import Path

from claude_metrics import run_claude
from prompts import MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1
from run_comparison import (
    MAIN_MODEL,
    NO_TOOLS_DISALLOWED,
    count_repo_leaks,
    run_reposcout,
    score_answer,
)

CHECK_SYMBOLS = ["InvestigationPlan", "EvidenceResult"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-run",
        type=Path,
        required=True,
        help="B3.1 run dir containing results.json and B3.1-<n>-plan.yaml",
    )
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--label", default="CP5", help="prefix for output files/dirs")
    args = parser.parse_args()
    label = args.label

    source_run = args.source_run.resolve()
    b3_1_report = json.loads((source_run / "results.json").read_text(encoding="utf-8"))
    b3_1_iter = b3_1_report["iterations"][args.iteration - 1]

    snapshot = Path(b3_1_report["snapshot"])
    if not snapshot.exists():
        raise SystemExit(
            f"snapshot no longer exists: {snapshot} (needed as cwd for the replay run)"
        )

    plan_path = source_run / f"B3.1-{args.iteration}-plan.yaml"
    if not plan_path.exists():
        raise SystemExit(f"plan not found: {plan_path}")

    old_evidence_path = source_run / f"B3.1-{args.iteration}-scout" / "evidence.md"
    old_evidence_chars = len(old_evidence_path.read_text(encoding="utf-8"))
    old_coverage = b3_1_iter["quality"]["coverage"]

    handoff = b3_1_iter["handoff"]
    repo_root = args.repo_root.resolve()
    output_dir = args.output or source_run / f"{label.lower()}-replay"
    output_dir.mkdir(parents=True, exist_ok=True)

    scout_output_dir = output_dir / f"{label}-{args.iteration}-scout"
    scout = run_reposcout(
        snapshot=snapshot,
        plan_path=plan_path,
        output_dir=scout_output_dir,
        repo_root=repo_root,
    )
    new_evidence = scout["evidence"]
    new_evidence_chars = len(new_evidence)
    growth_pct = (
        round((new_evidence_chars - old_evidence_chars) / old_evidence_chars * 100, 1)
        if old_evidence_chars
        else None
    )

    per_query_chars = {
        path.stem: len(json.loads(path.read_text(encoding="utf-8")).get("evidence", ""))
        for path in sorted(scout_output_dir.glob("Q*.json"))
    }

    symbol_hits = {symbol: symbol in new_evidence for symbol in CHECK_SYMBOLS}

    transcript = output_dir / f"{label}-{args.iteration}-main-final.jsonl"
    prompt = MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1.format(handoff=handoff, evidence=new_evidence)
    run = run_claude(
        prompt,
        label=f"{label}-main-final-{args.iteration}",
        root=snapshot,
        transcript_path=transcript,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (output_dir / f"{label}-{args.iteration}-answer.md").write_text(
        run.final_text, encoding="utf-8"
    )

    quality = score_answer(run.final_text)
    repo_leaks = count_repo_leaks(transcript, repo_root)

    result = {
        "label": label,
        "source_run": str(source_run),
        "source_iteration": args.iteration,
        "plan_path": str(plan_path),
        "old_evidence_chars": old_evidence_chars,
        "old_coverage": old_coverage,
        "new_evidence_chars": new_evidence_chars,
        "evidence_growth_pct": growth_pct,
        "per_query_evidence_chars": per_query_chars,
        "symbol_hits": symbol_hits,
        "query_count": scout["query_count"],
        "effective_query_count": scout["effective_query_count"],
        "failed_query_count": scout["failed_query_count"],
        "empty_evidence_count": scout["empty_evidence_count"],
        "additional_llm_calls": 0,  # structurally: only the Main final call runs here
        "coverage": quality["coverage"],
        "quality": quality,
        "main_final_input_tokens": run.total_input_tokens,
        "main_final_output_tokens": run.output_tokens,
        "incremental_cost_usd": round(run.cost_usd, 6),
        "elapsed_seconds": round(run.wall_seconds, 3),
        "repo_leaks": repo_leaks,
        "transcript_path": str(transcript),
    }

    json_path = output_dir / f"{label}-{args.iteration}-result.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("")
    print(f"B3.1 (rg match-line only) coverage: {old_coverage}")
    print(f"{label} coverage: {quality['coverage']}")
    print(f"evidence_chars: {old_evidence_chars} -> {new_evidence_chars} ({growth_pct}%)")
    print(f"per_query_evidence_chars: {per_query_chars}")
    print(f"symbol_hits: {symbol_hits}")

    if quality["coverage"] >= 1.0 and (growth_pct is None or growth_pct < 100):
        print("Verdict: CP5 pass -> coverage recovered with acceptable evidence growth.")
    elif quality["coverage"] < 1.0:
        print(
            "Verdict: coverage not recovered -> bounded context alone is not a "
            "sufficient Evidence Contract."
        )
    else:
        print(
            "Verdict: coverage recovered but evidence grew heavily -> revisit "
            "context expansion strategy."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
