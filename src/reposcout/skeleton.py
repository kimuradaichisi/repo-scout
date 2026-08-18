from pathlib import Path

from reposcout.executors.common import run_command

# Tracked paths only, matching the scope RepoScout's other executors operate
# within. Untracked and ignored files never appear here, so a query built
# from this list can only name a path that actually exists.
SKELETON_PATHS = ("src", "tests/unit")


class RepositorySkeleton:
    def list_files(self, root: Path) -> list[str]:
        code, stdout, stderr = run_command(root, ["git", "ls-files", *SKELETON_PATHS])
        if code != 0:
            raise RuntimeError(stderr.strip() or f"git ls-files exited with code {code}")
        return [line for line in stdout.strip().splitlines() if line]

    def as_text(self, root: Path) -> str:
        return "\n".join(self.list_files(root))

    def contains(self, root: Path, path: str) -> bool:
        return path in set(self.list_files(root))
