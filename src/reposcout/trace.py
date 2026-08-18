import json
from datetime import UTC, datetime
from pathlib import Path

from reposcout.models import InvestigationTrace, TraceMetrics


class TraceWriter:
    @staticmethod
    def new_trace(investigation_id: str, started_at: datetime | None = None) -> InvestigationTrace:
        return InvestigationTrace(
            investigation_id=investigation_id,
            started_at=started_at or datetime.now(UTC),
        )

    def write(self, path: Path, trace: InvestigationTrace) -> None:
        header = trace.model_dump(mode="json", exclude={"steps"})
        records = [
            {
                "record_type": "trace",
                "investigation_id": trace.investigation_id,
                "trace": header,
            }
        ]
        records.extend(
            {
                "record_type": "step",
                "investigation_id": trace.investigation_id,
                "step": step.model_dump(mode="json"),
            }
            for step in trace.steps
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
            + "\n",
            encoding="utf-8",
        )

    def read(self, path: Path) -> InvestigationTrace:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        header = next(record["trace"] for record in records if record["record_type"] == "trace")
        steps = [record["step"] for record in records if record["record_type"] == "step"]
        return InvestigationTrace.model_validate({**header, "steps": steps})


def summarize_trace(trace: InvestigationTrace) -> TraceMetrics:
    paths = [location.path for step in trace.steps for location in step.source_locations]
    metrics = TraceMetrics(
        search_count=sum(step.action == "search" for step in trace.steps),
        read_count=sum(step.action == "read" for step in trace.steps),
        pack_count=sum(step.action == "pack" for step in trace.steps),
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
