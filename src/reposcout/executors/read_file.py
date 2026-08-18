from pathlib import Path

from reposcout.executors.common import content_hash
from reposcout.models import EvidenceResult, InvestigationQuery, SourceLocation


class FileReadExecutor:
    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        assert query.file is not None
        path = (root / query.file).resolve()

        try:
            path.relative_to(root.resolve())
        except ValueError:
            return self._error(query, "file is outside repository root")

        if not path.is_file():
            return self._error(query, f"file not found: {query.file}")

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = (query.start_line or 1) - 1
        end = query.end_line or len(lines)
        selected = lines[start:end]

        numbered = [
            f"{line_number}:{line}" for line_number, line in enumerate(selected, start=start + 1)
        ]
        evidence = "\n".join(numbered)

        return EvidenceResult(
            query_id=query.id,
            status="PASS",
            executor="file_read",
            evidence=evidence,
            source_locations=self._locations(query.file, start, selected, evidence),
        )

    def _locations(
        self, file: str, start: int, selected: list[str], evidence: str
    ) -> list[SourceLocation]:
        # A requested range that runs past EOF is truncated by the slice
        # above; the location reflects what was actually read, not what was
        # asked for.
        if not selected:
            return []
        return [
            SourceLocation(
                path=file,
                start_line=start + 1,
                end_line=start + len(selected),
                content_hash=content_hash(evidence),
            )
        ]

    def _error(self, query: InvestigationQuery, message: str) -> EvidenceResult:
        return EvidenceResult(
            query_id=query.id,
            status="ERROR",
            executor="file_read",
            error=message,
        )
