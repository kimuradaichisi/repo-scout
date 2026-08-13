import subprocess
from pathlib import Path

from reposcout.models import EvidenceResult, InvestigationQuery
from reposcout.ornith.prompt import SYSTEM_PROMPT


class OrnithWorker:
    """
    Thin adapter around OpenCode.

    IMPORTANT:
    This intentionally starts a fresh process for every query so no previous
    conversation context is shared.

    Adjust `_build_command()` for your local OpenCode configuration.
    """

    def __init__(self, timeout_seconds: int = 180) -> None:
        self._timeout_seconds = timeout_seconds

    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        instruction = query.instruction or ""
        prompt = f"{SYSTEM_PROMPT}\n\nINVESTIGATION REQUEST:\n{instruction}"

        try:
            completed = subprocess.run(
                self._build_command(prompt),
                cwd=root,
                text=True,
                capture_output=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._error(query, str(exc))

        if completed.returncode != 0:
            return self._error(
                query,
                completed.stderr.strip() or f"OpenCode exited with {completed.returncode}",
            )

        return EvidenceResult(
            query_id=query.id,
            status="PASS",
            executor="ornith",
            evidence=completed.stdout.strip(),
        )

    def _build_command(self, prompt: str) -> list[str]:
        # Replace this command if your OpenCode CLI invocation differs.
        # Expected behavior: one non-interactive invocation using the configured
        # local Ornith model/agent and stdout as the final evidence.
        return ["opencode", "run", prompt]

    def _error(
        self,
        query: InvestigationQuery,
        message: str,
    ) -> EvidenceResult:
        return EvidenceResult(
            query_id=query.id,
            status="ERROR",
            executor="ornith",
            error=message,
        )
