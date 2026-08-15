"""CP4a: Same-Evidence Replay.

Isolates the effect of removing the Explorer synthesis step from the effect of
Explorer Plan variance (B3 and B3.1 each generated their own Plan, so their
RepoScout evidence differed and the two results were confounded).

This script generates NO new Explorer Plan and does NOT re-run RepoScout. It
reuses the exact evidence.md and handoff Brief already on disk from a B3 run
(the one that reached coverage=1.0) and feeds that evidence straight to
Main(Opus) final analysis, skipping the Sonnet synthesis call entirely:

    B3 (already run):   same Evidence -> Sonnet synthesis -> Main(Opus) final
    CP4a (this script):  same Evidence ->                 -> Main(Opus) final

synthesis presence/absence is the only variable that changes.
"""

import argparse
import hashlib
import json
from pathlib import Path

from claude_metrics import run_claude
from prompts import MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1
from run_comparison import MAIN_MODEL, NO_TOOLS_DISALLOWED, count_repo_leaks, score_answer


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-run",
        type=Path,
        required=True,
        help="B3 run dir containing results.json and B3-<n>-scout/evidence.md",
    )
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    source_run = args.source_run.resolve()
    b3_report = json.loads((source_run / "results.json").read_text(encoding="utf-8"))
    b3_iter = b3_report["iterations"][args.iteration - 1]

    snapshot = Path(b3_report["snapshot"])
    if not snapshot.exists():
        raise SystemExit(
            f"snapshot no longer exists: {snapshot} (needed as cwd for the replay run)"
        )

    evidence_path = source_run / f"B3-{args.iteration}-scout" / "evidence.md"
    evidence = evidence_path.read_text(encoding="utf-8")
    handoff = b3_iter["handoff"]

    b3_evidence_chars = b3_iter["reposcout"]["evidence_chars"]
    evidence_hash = sha256(evidence)
    evidence_matches_b3_record = len(evidence) == b3_evidence_chars
    if not evidence_matches_b3_record:
        print(
            f"WARNING: evidence length mismatch: replay={len(evidence)} chars "
            f"vs B3-recorded={b3_evidence_chars} chars"
        )

    repo_root = args.repo_root.resolve()
    output_dir = args.output or source_run / "cp4a-replay"
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript = output_dir / f"CP4a-{args.iteration}-main-final.jsonl"
    prompt = MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1.format(handoff=handoff, evidence=evidence)
    run = run_claude(
        prompt,
        label=f"CP4a-main-final-{args.iteration}",
        root=snapshot,
        transcript_path=transcript,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (output_dir / f"CP4a-{args.iteration}-answer.md").write_text(run.final_text, encoding="utf-8")

    quality = score_answer(run.final_text)
    repo_leaks = count_repo_leaks(transcript, repo_root)
    b3_coverage = b3_iter["quality"]["coverage"]

    result = {
        "source_run": str(source_run),
        "source_iteration": args.iteration,
        "evidence_path": str(evidence_path),
        "evidence_chars": len(evidence),
        "evidence_sha256": evidence_hash,
        "evidence_matches_b3_record": evidence_matches_b3_record,
        "handoff_chars": len(handoff),
        "b3_coverage": b3_coverage,
        "coverage": quality["coverage"],
        "quality": quality,
        "main_opus_input_tokens": run.total_input_tokens,
        "main_opus_output_tokens": run.output_tokens,
        "incremental_input_tokens": run.total_input_tokens,
        "incremental_output_tokens": run.output_tokens,
        "incremental_cost_usd": round(run.cost_usd, 6),
        "elapsed_seconds": round(run.wall_seconds, 3),
        "repo_leaks": repo_leaks,
        "transcript_path": str(transcript),
    }

    json_path = output_dir / f"CP4a-{args.iteration}-result.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("")
    print(f"B3 (with synthesis) coverage: {b3_coverage}")
    print(f"CP4a Replay (no synthesis) coverage: {quality['coverage']}")
    if quality["coverage"] >= 1.0:
        print(
            "Verdict: coverage 1.0 maintained -> synthesis stage judged unnecessary; "
            "B3.1 structure is a candidate."
        )
    else:
        print(
            "Verdict: coverage dropped -> synthesis has information-organizing value; "
            "simple removal not adopted."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
