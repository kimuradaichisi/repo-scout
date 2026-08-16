"""Fixed-condition hashes for a CP8 run.

Config A and Config B are only comparable while the things neither of them is
supposed to be varying stay byte-identical: the coding rules the Worker is
held to, the Worker's own definition, the hook that gates delegation, the
RepoScout adapter, and the source tree itself. Each run records their hashes
so that a comparison across runs can be shown to have held them fixed rather
than assumed it.
"""

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

# Relative to the snapshot. Everything here is a condition of the experiment,
# not a subject of it.
FIXED_FILES = {
    "claude_md": "CLAUDE.md",
    "subagent_def": ".claude/agents/sonnet-worker.md",
    "settings": ".claude/settings.json",
    "pre_worker_gate": ".claude/hooks/pre_worker_gate.sh",
    "role_gate": ".claude/hooks/role_gate.py",
    "scout": "scout",
}

SUBAGENT_MODEL_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"


def sha256_file(path: Path) -> str:
    if not path.exists():
        return "ABSENT"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_head(snapshot: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=snapshot,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() or "UNKNOWN"


def fixed_condition_hashes(snapshot: Path) -> dict[str, str]:
    """sha256 of every fixed condition, plus the snapshot commit they sit on."""
    hashes = {name: sha256_file(snapshot / rel) for name, rel in FIXED_FILES.items()}
    hashes["snapshot_head"] = snapshot_head(snapshot)
    return hashes


def claude_code_version() -> str:
    completed = subprocess.run(["claude", "--version"], text=True, capture_output=True, check=False)
    return completed.stdout.strip() or "UNKNOWN"


def subagent_model_env() -> str | None:
    """The env var that would override every subagent's model, if it is set.

    Returned rather than asserted: a run records what it saw, and the caller
    decides whether that is grounds to refuse to run.
    """
    return os.environ.get(SUBAGENT_MODEL_ENV)


def environment_record(snapshot: Path) -> dict[str, Any]:
    return {
        "claude_code_version": claude_code_version(),
        "subagent_model_env": subagent_model_env(),
        "subagent_model_env_unset": subagent_model_env() is None,
        "fixed_condition_hashes": fixed_condition_hashes(snapshot),
    }
