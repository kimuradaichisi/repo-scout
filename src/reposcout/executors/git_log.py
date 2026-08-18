from pathlib import Path

from reposcout.executors.common import run_command
from reposcout.models import EvidenceResult, InvestigationQuery


class GitLogExecutor:
    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        command = ["git", "log", "--oneline", "-20", *query.git_args]
        code, stdout, stderr = run_command(root, command)

        if code == 0:
            # Each line names a commit, not a file:line span -- there is no
            # source_location to confirm here without guessing which file the
            # caller means. source_locations stays [] rather than invented.
            return EvidenceResult(
                query_id=query.id,
                status="PASS",
                executor="git_log",
                evidence=stdout.strip(),
            )

        return EvidenceResult(
            query_id=query.id,
            status="ERROR",
            executor="git_log",
            error=stderr.strip() or f"git exited with code {code}",
        )
