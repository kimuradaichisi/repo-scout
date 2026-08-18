"""Snapshot lifecycle and the Main call, for CP9.

Snapshot construction, the hook logs and the role gate are CP8's and are
imported rather than reimplemented -- including the gate's environment
variable name, which stays CP8_ACTIVE_CONFIG. Renaming it would mean editing
.claude/hooks/role_gate.py, and that file is a frozen CP8 artifact whose hash
Step 0-B validated; a rename for tidiness would invalidate the one piece of
infrastructure CP9 most depends on being unchanged.

What CP9 owns is its own locked-hashes baseline, which covers the harness-side
definitions (task sizes, criteria, prompts, decision axes, gate thresholds) as
well as the snapshot's fixed files.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_metrics import run_claude
from cp8_step1_runtime import ACTIVE_CONFIG_ENV
from cp9_config import RunConfig
from cp9_hashes import LOCKED_HASHES_PATH, cp9_environment_record
from run_comparison import MAIN_MODEL


@dataclass
class RunPaths:
    snapshot: Path
    run_dir: Path
    label: str


def _drifted(locked: dict[str, str], current: dict[str, str], skip: tuple[str, ...]) -> list[str]:
    return [name for name in locked if name not in skip and locked[name] != current.get(name)]


def check_locked_hashes(repo_root: Path, snapshot: Path) -> dict[str, Any]:
    """Compare both hash sets against the CP9 baseline; snapshot_head is expected to differ."""
    experiments = repo_root / "tests/experiments"
    locked = json.loads((experiments / LOCKED_HASHES_PATH).read_text(encoding="utf-8"))
    current = cp9_environment_record(snapshot, experiments)
    drifted = _drifted(
        locked["fixed_condition_hashes"], current["fixed_condition_hashes"], ("snapshot_head",)
    )
    drifted += [
        f"cp9:{name}"
        for name in _drifted(locked["cp9_definition_hashes"], current["cp9_definition_hashes"], ())
    ]
    return {"current": current, "drifted": drifted, "matches_locked": not drifted}


def run_main(prompt: str, config: RunConfig, paths: RunPaths) -> tuple[Any, Path]:
    """Run Main with the role gate's config set for exactly this call.

    Set immediately before run_claude's subprocess.run, which inherits the
    harness environment, and cleared in finally so nothing downstream of this
    run -- another run, a grader call -- can inherit a stale value.
    """
    transcript = paths.run_dir / f"{paths.label}.jsonl"
    os.environ[ACTIVE_CONFIG_ENV] = config.key
    try:
        run = run_claude(
            prompt,
            label=paths.label,
            root=paths.snapshot,
            transcript_path=transcript,
            model=MAIN_MODEL,
            allowed_tools=config.allowed_tools,
            disallowed_tools=config.disallowed_tools,
            timeout_seconds=2700,
        )
    finally:
        os.environ.pop(ACTIVE_CONFIG_ENV, None)
    (paths.run_dir / f"{paths.label}-answer.md").write_text(run.final_text, encoding="utf-8")
    return run, transcript
