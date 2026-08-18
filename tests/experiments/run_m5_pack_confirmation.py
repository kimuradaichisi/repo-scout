"""M5: one-shot paired confirmation that Pack First reduces repeated reads.

Exactly two model calls total (Control, then Pack First), both Sonnet, both
against independent clean snapshots of the same commit -- see the module
docstrings of m5_task/m5_report/m5_compare for what each half measures. This
is a product closing confirmation, not a new generalization study: no retry,
no third condition, no size variation.
"""

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_metrics import run_claude
from m5_compare import compare
from m5_report import build_report
from m5_task import control_prompt, pack_first_prompt
from run_comparison import build_snapshot

MODEL = "claude-sonnet-5"
ALLOWED_TOOLS = "Read,Grep,Glob,Bash"
DISALLOWED_TOOLS = "Write,Edit,Task,WebFetch,WebSearch"

CONDITIONS = (
    ("control", control_prompt),
    ("pack_first", pack_first_prompt),
)


def _commit_sha(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def _prepare_snapshot(repo_root: Path, dest: Path) -> Path:
    snapshot = build_snapshot(repo_root, dest)
    (snapshot / "CLAUDE.md").write_text(
        (repo_root / "CLAUDE.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=snapshot, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=experiment",
            "-c",
            "user.email=experiment@local",
            "commit",
            "-qm",
            "add CLAUDE.md",
        ],
        cwd=snapshot,
        check=True,
    )
    return snapshot


def _run_condition(
    label: str,
    prompt_fn: Any,
    repo_root: Path,
    snapshot_root: Path,
    run_dir: Path,
) -> dict[str, Any]:
    snapshot = _prepare_snapshot(repo_root, snapshot_root / label / "target")
    transcript = run_dir / f"{label}.jsonl"
    print(f"  -> {label}")
    run = run_claude(
        prompt_fn(),
        label=label,
        root=snapshot,
        transcript_path=transcript,
        model=MODEL,
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
    )
    (run_dir / f"{label}-answer.md").write_text(run.final_text, encoding="utf-8")
    report = build_report(label, run, transcript, snapshot, repo_root)
    coverage = report["quality"]["coverage"]
    repeats = report["primary_metrics"]["repeated_read_calls"]
    print(f"     coverage={coverage} repeated_read_calls={repeats}")
    return report


def _build_payload(repo_root: Path, reports: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant": "m5-pack-confirmation",
        "fixed_conditions": {
            "commit": _commit_sha(repo_root),
            "model": MODEL,
            "allowed_tools": ALLOWED_TOOLS,
            "disallowed_tools": DISALLOWED_TOOLS,
        },
        "reports": reports,
        "comparison": compare(reports["control"], reports["pack_first"]),
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = repo_root / "tests/experiments/results" / f"{stamp}-m5-pack-confirmation"
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot_root = Path(tempfile.gettempdir()) / f"reposcout-m5-{stamp}"

    print("=== M5: Pack First one-shot paired confirmation ===")
    reports = {
        label: _run_condition(label, prompt_fn, repo_root, snapshot_root, run_dir)
        for label, prompt_fn in CONDITIONS
    }
    payload = _build_payload(repo_root, reports)

    out_path = run_dir / "m5-results.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print(f"\nJSON: {out_path}")
    print(f"interpretation: {payload['comparison']['interpretation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
