import json
from datetime import UTC, datetime
from pathlib import Path

from reposcout.models import InvestigationStep, InvestigationTrace, TraceMetrics


class TraceWriter:
    """Appends one JSONL record per call, not a single batched write.

    JSONL was chosen so partial progress survives a crash mid-investigation;
    start()/append_step()/complete() each flush immediately, so a step is on
    disk the instant it happens rather than only once the whole investigation
    finishes.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @staticmethod
    def new_trace(investigation_id: str, started_at: datetime | None = None) -> InvestigationTrace:
        return InvestigationTrace(
            investigation_id=investigation_id,
            started_at=started_at or datetime.now(UTC),
        )

    def start(self, trace: InvestigationTrace) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._append(
            {
                "record_type": "trace",
                "investigation_id": trace.investigation_id,
                "trace": trace.model_dump(mode="json", exclude={"steps"}),
            }
        )

    def append_step(self, trace: InvestigationTrace, step: InvestigationStep) -> None:
        self._append(
            {
                "record_type": "step",
                "investigation_id": trace.investigation_id,
                "step": step.model_dump(mode="json"),
            }
        )

    def complete(self, trace: InvestigationTrace) -> None:
        trace.completed_at = trace.completed_at or datetime.now(UTC)
        self._append(
            {
                "record_type": "complete",
                "investigation_id": trace.investigation_id,
                "completed_at": trace.completed_at.isoformat(),
            }
        )

    def _append(self, record: dict[str, object]) -> None:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def read(self, path: Path) -> InvestigationTrace:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        header = next(record["trace"] for record in records if record["record_type"] == "trace")
        steps = [record["step"] for record in records if record["record_type"] == "step"]
        completed = next(
            (r["completed_at"] for r in records if r["record_type"] == "complete"), None
        )
        data = {**header, "steps": steps}
        if completed:
            data["completed_at"] = completed
        return InvestigationTrace.model_validate(data)


def summarize_trace(trace: InvestigationTrace) -> TraceMetrics:
    paths = [location.path for step in trace.steps for location in step.source_locations]
    metrics = TraceMetrics(
        search_count=sum(step.action == "search" for step in trace.steps),
        read_count=sum(step.action == "read" for step in trace.steps),
        git_count=sum(step.action == "git_log" for step in trace.steps),
        pack_count=sum(step.action == "pack" for step in trace.steps),
        semantic_explore_count=sum(step.action == "semantic_explore" for step in trace.steps),
        unique_paths=len(set(paths)),
        repeated_paths=sum(paths.count(path) > 1 for path in set(paths)),
        unresolved_count=sum(step.status == "UNRESOLVED" for step in trace.steps),
        error_count=sum(step.status == "ERROR" for step in trace.steps),
        tool_calls=sum(step.action != "stop" for step in trace.steps),
        elapsed_ms=sum(step.elapsed_ms or 0 for step in trace.steps),
    )
    for step in trace.steps:
        if step.pack_metrics:
            metrics.requested_source_bytes += step.pack_metrics.requested_source_bytes
            metrics.packed_source_bytes += step.pack_metrics.packed_source_bytes
            metrics.duplicate_or_overlap_bytes_eliminated += (
                step.pack_metrics.duplicate_or_overlap_bytes_eliminated
            )
            metrics.pack_chars += step.pack_metrics.pack_chars
    return metrics
