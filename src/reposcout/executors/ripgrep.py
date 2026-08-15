from pathlib import Path

from reposcout.executors.common import run_command
from reposcout.models import EvidenceResult, InvestigationQuery


class RipgrepExecutor:
    # A match line alone is a locator, not evidence: multi-line constructs
    # (import blocks, signatures, decorators) routinely span past it. Bounded
    # context turns each match into a self-contained excerpt without an extra
    # LLM round-trip; rg merges overlapping/adjacent windows on its own.
    #
    # Applying context to every query blew Evidence up 8-10x on broad,
    # multi-file sweeps that didn't need it (CP5). A query scoped to a small,
    # explicit file set is asking "what does this look like here" and gets
    # context; a query fanning out across many files is asking "where is
    # this" and stays locator-only (CP5b).
    CONTEXT_LINES = 5
    NARROW_PATH_THRESHOLD = 3

    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        command = ["rg", "--line-number", "--no-heading"]
        if 0 < len(query.paths) <= self.NARROW_PATH_THRESHOLD:
            command.extend(["--context", str(self.CONTEXT_LINES)])
        command.append(query.pattern or "")
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
