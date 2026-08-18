"""Materialize CP8's fixed conditions into a snapshot.

CP0-CP7 investigated a snapshot that contained no CLAUDE.md, which was
harmless while nothing was being written. CP8 grades implementation quality
against those rules, so the rules have to be present, and so do the Worker
definition, the delegation gate, and the RepoScout adapter. All four are
conditions of the experiment: they are copied in, committed, and hashed
(cp8_hashes.py), never authored by a run.

The snapshot also gets its own virtualenv, so `uv run pytest` inside it tests
the snapshot's code through the snapshot's own environment and never reaches
back to the repository the snapshot was taken from.
"""

import os
import shutil
import subprocess
from pathlib import Path

from run_comparison import build_snapshot

TEMPLATES = Path(__file__).resolve().parent / "cp8_templates"

# template file -> destination inside the snapshot
TEMPLATE_TARGETS = {
    "sonnet-worker.md": ".claude/agents/sonnet-worker.md",
    "settings.json": ".claude/settings.json",
    "pre_worker_gate.sh": ".claude/hooks/pre_worker_gate.sh",
    "role_gate.py": ".claude/hooks/role_gate.py",
    "scout": "scout",
    "gitignore": ".gitignore",
}
EXECUTABLES = (
    "scout",
    ".claude/hooks/pre_worker_gate.sh",
    ".claude/hooks/role_gate.py",
)

REPOSCOUT_BIN_ENV = "REPOSCOUT_BIN"


def _copy_templates(snapshot: Path) -> None:
    for name, relative in TEMPLATE_TARGETS.items():
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TEMPLATES / name, destination)
    for relative in EXECUTABLES:
        (snapshot / relative).chmod(0o755)


def _copy_claude_md(repo_root: Path, snapshot: Path) -> None:
    """Copy the coding rules the Worker will be held to.

    Absence is fatal rather than skipped: a run whose acceptance criteria cite
    rules the Worker never saw would look like a quality result and be one.
    """
    source = repo_root / "CLAUDE.md"
    if not source.exists():
        raise FileNotFoundError(f"CLAUDE.md not found at {source}; CP8 requires it in the snapshot")
    shutil.copy2(source, snapshot / "CLAUDE.md")


def _commit_fixtures(snapshot: Path) -> None:
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
            "cp8 fixed conditions",
        ],
        cwd=snapshot,
        check=True,
    )


def sync_snapshot_env(snapshot: Path) -> subprocess.CompletedProcess[str]:
    """Give the snapshot its own venv so the quality gates run inside it."""
    return subprocess.run(
        ["uv", "sync", "--extra", "dev"],
        cwd=snapshot,
        text=True,
        capture_output=True,
        check=False,
    )


def read_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def working_tree_status(snapshot: Path) -> str:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=snapshot,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip()


def reset_working_tree(snapshot: Path) -> None:
    """Return the snapshot to its committed state between probes."""
    subprocess.run(["git", "reset", "--hard", "-q"], cwd=snapshot, check=True)
    subprocess.run(["git", "clean", "-fdq"], cwd=snapshot, check=True)


def inject_reposcout_bin(repo_root: Path) -> Path:
    """Publish the RepoScout executable to ./scout through the environment.

    This is the harness half of the adapter: the snapshot's `scout` reads
    REPOSCOUT_BIN, so the path exists in the process environment but not in any
    file a run can read.
    """
    binary = repo_root / ".venv" / "bin" / "reposcout"
    if not binary.exists():
        raise FileNotFoundError(f"RepoScout executable not found at {binary}; run `make install`")
    os.environ[REPOSCOUT_BIN_ENV] = str(binary)
    return binary


def isolate_environment(repo_root: Path, snapshot: Path) -> dict[str, str]:
    """Remove the harness's own repository from the environment a run inherits.

    The harness runs under `uv run`, which leaves VIRTUAL_ENV and a PATH entry
    pointing at the real repository behind. Inside the snapshot, uv notices the
    mismatch and prints the real path in a warning on every single gate
    command -- which lands in Main's transcript and is exactly what
    count_repo_leaks exists to catch. uv, claude and git all live outside the
    repository, so dropping those entries costs nothing.
    """
    removed = {"VIRTUAL_ENV": os.environ.pop("VIRTUAL_ENV", "")}
    kept = [
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and not Path(entry).is_relative_to(repo_root)
    ]
    removed["PATH"] = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(kept)
    os.environ["PWD"] = str(snapshot)
    return removed


def prepare_snapshot(repo_root: Path, destination: Path) -> Path:
    """Build a snapshot and install every fixed condition into it."""
    snapshot = build_snapshot(repo_root, destination)
    _copy_claude_md(repo_root, snapshot)
    _copy_templates(snapshot)
    _commit_fixtures(snapshot)
    return snapshot
