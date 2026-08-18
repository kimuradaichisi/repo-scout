import time
import uuid
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
    InvestigationStep,
    InvestigationTrace,
    QueryTool,
    TraceAction,
)
from reposcout.ornith.client import OrnithWorker
from reposcout.trace import TraceWriter


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
        investigation_id: str | None = None,
        trace_out: Path | None = None,
    ) -> list[EvidenceResult]:
        run_dir.mkdir(parents=True, exist_ok=True)
        self._writer.write_plan(run_dir, plan)
        trace, trace_writer = self._start_trace(investigation_id, trace_out)

        results: list[EvidenceResult] = []

        for query in plan.queries:
            started = time.perf_counter()
            result = self._query_runner.execute(root, query)
            self._writer.write_result(run_dir, result)
            results.append(result)
            if trace is not None:
                step = self._record_query(trace, query, result, time.perf_counter() - started)
                if trace_writer is not None:
                    trace_writer.append_step(trace, step)

        self._writer.write_pack(run_dir, plan, results)
        self._writer.write_contract(run_dir, self._writer.build_contract(plan, results))
        self._finish_trace(trace, trace_writer)
        return results

    def _start_trace(
        self, investigation_id: str | None, trace_out: Path | None
    ) -> tuple[InvestigationTrace | None, TraceWriter | None]:
        if trace_out is None:
            return None, None
        trace = TraceWriter.new_trace(investigation_id or f"reposcout-{uuid.uuid4().hex}")
        writer = TraceWriter(trace_out)
        writer.start(trace)
        return trace, writer

    def _finish_trace(self, trace: InvestigationTrace | None, writer: TraceWriter | None) -> None:
        if trace is None or writer is None:
            return
        stop_step = trace.add_step(action="stop", executor="investigation", status="PASS")
        writer.append_step(trace, stop_step)
        writer.complete(trace)

    def _record_query(
        self,
        trace: InvestigationTrace,
        query: InvestigationQuery,
        result: EvidenceResult,
        elapsed: float,
    ) -> InvestigationStep:
        action = self._trace_action(query, result)
        return trace.add_step(
            action=action,
            executor=result.executor,
            status=result.status,
            query_id=query.id,
            target_kind=query.tool.value if query.tool else None,
            target_value=query.file or query.pattern,
            result_count=(
                result.result_count
                if result.result_count is not None
                else self._line_count(result.evidence)
            ),
            elapsed_ms=max(0, round(elapsed * 1000)),
            input_bytes=result.input_bytes,
            output_bytes=(
                result.output_bytes
                if result.output_bytes is not None
                else len(result.evidence.encode("utf-8"))
            ),
            source_locations=result.source_locations,
        )

    def _trace_action(self, query: InvestigationQuery, result: EvidenceResult) -> TraceAction:
        if result.status == "UNRESOLVED":
            return "unresolved"
        if result.status == "ERROR":
            return "error"
        if query.tool is None:
            return "error"
        actions: dict[QueryTool, TraceAction] = {
            QueryTool.RG: "search",
            QueryTool.READ: "read",
            QueryTool.GIT_LOG: "git_log",
            QueryTool.ORNITH: "semantic_explore",
        }
        return actions[query.tool]

    def _line_count(self, evidence: str) -> int:
        return len(evidence.splitlines())
