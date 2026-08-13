from pathlib import Path

from reposcout.executors.common import run_command
from reposcout.models import EvidenceResult, InvestigationQuery


class RipgrepExecutor:
    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        command = ["rg", "--line-number", "--no-heading", query.pattern or ""]
        command.extend(query.paths)

        code, stdout, stderr = run_command(root, command)
        if code in {0, 1}:
            return EvidenceResult(
                query_id=query.id,
                status="PASS",
                executor="ripgrep",
                evidence=stdout.strip(),
            )

        return EvidenceResult(
            query_id=query.id,
            status="ERROR",
            executor="ripgrep",
            error=stderr.strip() or f"rg exited with code {code}",
        )
