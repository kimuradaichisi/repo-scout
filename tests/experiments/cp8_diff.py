"""Deterministic changed-path detection for a CP8 Step 1 run.

The first Step 1 batch (2026-08-16, run 20260816-145853-cp8-step1) computed
changed_paths from `git diff --name-only HEAD` alone. That only shows tracked
files, so every task's actual deliverable -- a brand-new test file -- was
invisible: `git status --porcelain` showed `?? tests/unit/test_ripgrep.py`
while `git diff --name-only HEAD` returned nothing. All six runs'
expected_files_present / diff_scope_violation_count / acceptance_criteria_met
were computed against an empty or partial view of what actually changed.

changed_paths is now the union of two git operations, neither of which
touches the index (verified: `git status --porcelain` is byte-identical
before and after both):

    tracked   git diff --name-only HEAD          (modified + deleted)
    untracked git ls-files --others --exclude-standard   (new files)

The diff *text* handed to the grader gets the same union treatment: tracked
changes come from `git diff HEAD` as before; each untracked file is rendered
as its own new-file diff via `git diff --no-index -- /dev/null <path>`, which
also never touches the index -- it treats both paths as plain files, entirely
outside git's tracked/staged machinery.
"""

import subprocess
from pathlib import Path


def _run(args: list[str], snapshot: Path) -> str:
    return subprocess.run(args, cwd=snapshot, text=True, capture_output=True, check=False).stdout


def tracked_diff_text(snapshot: Path) -> str:
    return _run(["git", "diff", "HEAD"], snapshot)


def tracked_changed_names(snapshot: Path) -> list[str]:
    """Modified and deleted tracked paths, relative to the fixture commit."""
    return [
        line for line in _run(["git", "diff", "--name-only", "HEAD"], snapshot).splitlines() if line
    ]


def untracked_names(snapshot: Path) -> list[str]:
    """New files nothing in the fixture commit knows about, .gitignore excluded."""
    return [
        line
        for line in _run(
            ["git", "ls-files", "--others", "--exclude-standard"], snapshot
        ).splitlines()
        if line
    ]


def untracked_diff_text(snapshot: Path, names: list[str]) -> str:
    """One new-file diff per untracked path, concatenated. Index untouched."""
    sections = [
        _run(["git", "diff", "--no-index", "--", "/dev/null", name], snapshot) for name in names
    ]
    return "\n".join(section for section in sections if section)


def diff_against_fixture_commit(snapshot: Path) -> tuple[str, list[str]]:
    """Unified diff text and changed paths, covering tracked and untracked files.

    Returns (diff_text, changed_paths) with changed_paths deduplicated and
    sorted, so a file that is somehow both listed (should not happen, but
    isn't assumed) contributes one entry, not two.
    """
    tracked_names = tracked_changed_names(snapshot)
    new_names = untracked_names(snapshot)
    diff_text = tracked_diff_text(snapshot)
    untracked_section = untracked_diff_text(snapshot, new_names)
    if untracked_section:
        diff_text = f"{diff_text}\n{untracked_section}" if diff_text else untracked_section
    return diff_text, sorted(set(tracked_names) | set(new_names))
