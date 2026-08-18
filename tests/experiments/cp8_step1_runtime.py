"""Snapshot lifecycle and the Main call itself, for CP8 Step 1.

Split out of run_cp8_step1.py so the orchestrator reads as the six-run loop
it is, not as loop-plus-plumbing. _check_locked_hashes is the drift gate rev.2
asked for: every run's fixed-condition hashes are compared against the
baseline recorded right after the Preparation commit, and a run whose
infrastructure has drifted is marked aborted rather than folded into the
comparison as if nothing had changed.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_metrics import run_claude
from cp8_fixtures import prepare_snapshot, sync_snapshot_env
from cp8_hashes import environment_record
from cp8_step1_config import StepConfig
from run_comparison import MAIN_MODEL

ROLE_LOG = ".cp8/role_gate.log"
PRE_WORKER_LOG = ".cp8/pre_worker_gate.log"
LOCKED_HASHES_PATH = "results/cp8-step1-fixed-infrastructure/locked-hashes.json"
ACTIVE_CONFIG_ENV = "CP8_ACTIVE_CONFIG"


@dataclass
class RunPaths:
    snapshot: Path
    run_dir: Path
    label: str


def clear_hook_logs(snapshot: Path) -> None:
    for relative in (ROLE_LOG, PRE_WORKER_LOG):
        (snapshot / relative).unlink(missing_ok=True)


def setup_snapshot(repo_root: Path, dest: Path) -> Path:
    snapshot = prepare_snapshot(repo_root, dest)
    sync = sync_snapshot_env(snapshot)
    if sync.returncode != 0:
        raise RuntimeError(f"uv sync failed for {snapshot}: {sync.stderr[-2000:]}")
    return snapshot


def check_locked_hashes(repo_root: Path, snapshot: Path) -> dict[str, Any]:
    locked = json.loads((repo_root / "tests/experiments" / LOCKED_HASHES_PATH).read_text())
    current = environment_record(snapshot)
    locked_hashes = locked["fixed_condition_hashes"]
    current_hashes = current["fixed_condition_hashes"]
    drifted = [
        name
        for name in locked_hashes
        if name != "snapshot_head" and locked_hashes[name] != current_hashes.get(name)
    ]
    return {"current": current, "drifted": drifted, "matches_locked": not drifted}


def run_main(prompt: str, label: str, config: StepConfig, snapshot: Path, run_dir: Path) -> Any:
    """Run Main with CP8_ACTIVE_CONFIG set for exactly this call.

    Set immediately before run_claude's subprocess.run (which inherits the
    harness's os.environ) and cleared in finally, so neither an earlier run
    nor the grader call that follows this one can inherit a stale value.
    """
    transcript = run_dir / f"{label}.jsonl"
    os.environ[ACTIVE_CONFIG_ENV] = config.key
    try:
        run = run_claude(
            prompt,
            label=label,
            root=snapshot,
            transcript_path=transcript,
            model=MAIN_MODEL,
            allowed_tools=config.allowed_tools,
            disallowed_tools=config.disallowed_tools,
            timeout_seconds=1800,
        )
    finally:
        os.environ.pop(ACTIVE_CONFIG_ENV, None)
    (run_dir / f"{label}-answer.md").write_text(run.final_text, encoding="utf-8")
    return run, transcript
