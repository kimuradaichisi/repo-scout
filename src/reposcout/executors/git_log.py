from pathlib import Path

from reposcout.executors.common import run_command
from reposcout.models import EvidenceResult, InvestigationQuery


class GitLogExecutor:
    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        command = ["git", "log", "--oneline", "-20", *query.git_args]
        code, stdout, stderr = run_command(root, command)

        if code == 0:
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
