from pathlib import Path
from typing import Protocol

from reposcout.models import EvidenceResult, InvestigationQuery


class QueryExecutor(Protocol):
    def execute(
        self,
        root: Path,
        query: InvestigationQuery,
    ) -> EvidenceResult: ...
