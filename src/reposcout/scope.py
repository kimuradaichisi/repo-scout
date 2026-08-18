from enum import StrEnum
from pathlib import Path

from reposcout.executors.common import run_command

# Directories RepoScout operates within. Not a repository-wide scope: a query
# built from this list can only name a path that actually exists inside it.
SCOPE_PATHS = ("src", "tests/unit")


class FileScopeMode(StrEnum):
    """Which files `git ls-files` reports.

    Git's own .gitignore matching is the source of truth for both modes --
    neither hard-codes directory names like node_modules/.venv, so scope
    stays correct as the repository's ignore rules change.
    """

    TRACKED_ONLY = "tracked-only"
    WORKSPACE = "workspace"


_MODE_ARGS: dict[FileScopeMode, tuple[str, ...]] = {
    FileScopeMode.TRACKED_ONLY: (),
    FileScopeMode.WORKSPACE: ("--cached", "--others", "--exclude-standard"),
}


class RepositoryFileScope:
    """The deterministic file universe Skeleton and Pack both validate against.

    tracked-only (default) is git-tracked files only. workspace adds
    untracked-but-not-ignored files (git ls-files --others --exclude-standard)
    -- still nothing Git itself would not already report as in-scope.
    """

    def __init__(self, mode: FileScopeMode = FileScopeMode.TRACKED_ONLY) -> None:
        self._mode = mode

    def list_files(self, root: Path) -> list[str]:
        command = ["git", "ls-files", *_MODE_ARGS[self._mode], *SCOPE_PATHS]
        code, stdout, stderr = run_command(root, command)
        if code != 0:
            raise RuntimeError(stderr.strip() or f"git ls-files exited with code {code}")
        return [line for line in stdout.strip().splitlines() if line]

    def as_text(self, root: Path) -> str:
        return "\n".join(self.list_files(root))

    def contains(self, root: Path, path: str) -> bool:
        return path in set(self.list_files(root))
