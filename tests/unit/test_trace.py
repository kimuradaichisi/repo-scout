from datetime import UTC, datetime

from reposcout.models import PackMetrics, SourceLocation
from reposcout.trace import TraceWriter, summarize_trace


def test_trace_jsonl_round_trip_keeps_order_and_metadata(tmp_path) -> None:
    trace = TraceWriter.new_trace("inv-1", datetime.now(UTC))
    trace.add_step(
        action="search",
        executor="ripgrep",
        status="PASS",
        query_id="Q1",
        result_count=2,
        elapsed_ms=3,
        source_locations=[SourceLocation(path="src/a.py", start_line=4, end_line=4)],
    )
    trace.add_step(
        action="unresolved",
        executor="none",
        status="UNRESOLVED",
        query_id="Q2",
        elapsed_ms=0,
    )
    trace.add_step(
        action="pack",
        executor="pack",
        status="PASS",
        pack_metrics=PackMetrics(
            requested_ranges=2,
            packed_ranges=1,
            requested_source_bytes=20,
            packed_source_bytes=10,
            duplicate_or_overlap_bytes_eliminated=10,
            unique_paths=1,
            pack_chars=10,
        ),
    )

    path = tmp_path / "trace.jsonl"
    TraceWriter().write(path, trace)
    loaded = TraceWriter().read(path)

    assert loaded.investigation_id == "inv-1"
    assert [step.sequence for step in loaded.steps] == [1, 2, 3]
    assert loaded.steps[0].source_locations[0].path == "src/a.py"
    assert loaded.steps[1].status == "UNRESOLVED"
    assert loaded.steps[2].pack_metrics is not None
    assert "source content" not in path.read_text(encoding="utf-8")


def test_trace_step_elapsed_is_non_negative() -> None:
    trace = TraceWriter.new_trace("inv-2", datetime.now(UTC))

    step = trace.add_step(action="error", executor="read", status="ERROR", elapsed_ms=0)

    assert step.elapsed_ms is not None
    assert step.elapsed_ms >= 0


def test_trace_summary_is_deterministic_from_step_metadata() -> None:
    trace = TraceWriter.new_trace("inv-3", datetime.now(UTC))
    location = SourceLocation(path="src/a.py", start_line=1, end_line=1)
    trace.add_step(
        action="search",
        executor="rg",
        status="PASS",
        elapsed_ms=4,
        source_locations=[location],
    )
    trace.add_step(
        action="read",
        executor="read",
        status="ERROR",
        elapsed_ms=2,
        source_locations=[location],
    )

    summary = summarize_trace(trace)

    assert summary.search_count == 1
    assert summary.read_count == 1
    assert summary.unique_paths == 1
    assert summary.repeated_paths == 1
    assert summary.error_count == 1
    assert summary.tool_calls == 2
    assert summary.elapsed_ms == 6
