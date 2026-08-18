from pathlib import Path

from reposcout.evidence import EvidenceWriter
from reposcout.executors.base import QueryExecutor
from reposcout.executors.git_log import GitLogExecutor
from reposcout.executors.read_file import FileReadExecutor
from reposcout.executors.ripgrep import RipgrepExecutor
from reposcout.models import (
    EvidenceResult,
    InvestigationPlan,
    InvestigationQuery,
    QueryTool,
)
from reposcout.ornith.client import OrnithWorker


class QueryRunner:
    """Dispatches to a deterministic executor, or to Ornith when explicitly
    asked (tool="ornith"). It never picks Ornith on RepoScout's own judgment:
    a query with no tool, or one naming a tool RepoScout has no executor for,
    comes back UNRESOLVED rather than being guessed at semantically.
    """

    def __init__(self, ornith_worker: OrnithWorker | None = None) -> None:
        self._ornith = ornith_worker or OrnithWorker()
        self._executors: dict[QueryTool, QueryExecutor] = {
            QueryTool.RG: RipgrepExecutor(),
            QueryTool.READ: FileReadExecutor(),
            QueryTool.GIT_LOG: GitLogExecutor(),
        }

    def execute(
        self,
        root: Path,
        query: InvestigationQuery,
    ) -> EvidenceResult:
        if query.tool == QueryTool.ORNITH:
            return self._ornith.execute(root, query)

        if query.tool in self._executors:
            return self._executors[query.tool].execute(root, query)

        return self._unresolved(query)

    def _unresolved(self, query: InvestigationQuery) -> EvidenceResult:
        return EvidenceResult(
            query_id=query.id,
            status="UNRESOLVED",
            executor="none",
            error=(
                "no deterministic tool specified; RepoScout does not choose a "
                'semantic explorer on its own -- set tool="ornith" explicitly '
                "to opt into LLM exploration"
            ),
        )


class InvestigationRunner:
    def __init__(
        self,
        query_runner: QueryRunner | None = None,
        evidence_writer: EvidenceWriter | None = None,
    ) -> None:
        self._query_runner = query_runner or QueryRunner()
        self._writer = evidence_writer or EvidenceWriter()

    def execute(
        self,
        root: Path,
        plan: InvestigationPlan,
        run_dir: Path,
    ) -> list[EvidenceResult]:
        run_dir.mkdir(parents=True, exist_ok=True)
        self._writer.write_plan(run_dir, plan)

        results: list[EvidenceResult] = []

        for query in plan.queries:
            result = self._query_runner.execute(root, query)
            self._writer.write_result(run_dir, result)
            results.append(result)

        self._writer.write_pack(run_dir, plan, results)
        return results
