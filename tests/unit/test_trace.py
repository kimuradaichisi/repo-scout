import json
from datetime import UTC, datetime

from reposcout.models import PackMetrics, SourceLocation
from reposcout.trace import TraceWriter, summarize_trace


def test_trace_start_persists_header_before_any_step(tmp_path) -> None:
    trace = TraceWriter.new_trace("inv-1", datetime.now(UTC))
    path = tmp_path / "trace.jsonl"

    TraceWriter(path).start(trace)

    assert path.is_file()
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["record_type"] for r in records] == ["trace"]


def test_append_step_is_on_disk_immediately(tmp_path) -> None:
    trace = TraceWriter.new_trace("inv-1", datetime.now(UTC))
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.start(trace)

    step = trace.add_step(action="search", executor="ripgrep", status="PASS")
    writer.append_step(trace, step)

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["record_type"] for r in records] == ["trace", "step"]
    assert records[1]["step"]["action"] == "search"


def test_second_step_append_keeps_the_first_on_disk(tmp_path) -> None:
    trace = TraceWriter.new_trace("inv-1", datetime.now(UTC))
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.start(trace)

    first = trace.add_step(action="search", executor="ripgrep", status="PASS")
    writer.append_step(trace, first)
    second = trace.add_step(action="read", executor="read", status="PASS")
    writer.append_step(trace, second)

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["record_type"] for r in records] == ["trace", "step", "step"]
    assert [r["step"]["sequence"] for r in records[1:]] == [1, 2]


def test_file_is_valid_jsonl_before_complete_is_called(tmp_path) -> None:
    trace = TraceWriter.new_trace("inv-1", datetime.now(UTC))
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.start(trace)
    writer.append_step(trace, trace.add_step(action="search", executor="ripgrep", status="PASS"))

    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        json.loads(line)  # each line parses standalone -- no trailing/partial record

    assert not any(record.get("record_type") == "complete" for record in map(json.loads, lines))


def test_complete_appends_completion_metadata(tmp_path) -> None:
    trace = TraceWriter.new_trace("inv-1", datetime.now(UTC))
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.start(trace)

    writer.complete(trace)

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["record_type"] == "complete"
    assert records[-1]["completed_at"] is not None


def test_trace_jsonl_round_trip_keeps_order_and_metadata(tmp_path) -> None:
    trace = TraceWriter.new_trace("inv-1", datetime.now(UTC))
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.start(trace)

    writer.append_step(
        trace,
        trace.add_step(
            action="search",
            executor="ripgrep",
            status="PASS",
            query_id="Q1",
            result_count=2,
            elapsed_ms=3,
            source_locations=[SourceLocation(path="src/a.py", start_line=4, end_line=4)],
        ),
    )
    writer.append_step(
        trace,
        trace.add_step(
            action="unresolved", executor="none", status="UNRESOLVED", query_id="Q2", elapsed_ms=0
        ),
    )
    writer.append_step(
        trace,
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
        ),
    )
    writer.complete(trace)

    loaded = TraceWriter(path).read(path)

    assert loaded.investigation_id == "inv-1"
    assert [step.sequence for step in loaded.steps] == [1, 2, 3]
    assert loaded.steps[0].source_locations[0].path == "src/a.py"
    assert loaded.steps[1].status == "UNRESOLVED"
    assert loaded.steps[2].pack_metrics is not None
    assert loaded.completed_at is not None
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


def test_trace_summary_distinguishes_semantic_explore_from_search() -> None:
    trace = TraceWriter.new_trace("inv-4", datetime.now(UTC))
    trace.add_step(action="search", executor="ripgrep", status="PASS")
    trace.add_step(action="semantic_explore", executor="ornith", status="PASS")
    trace.add_step(action="git_log", executor="git_log", status="PASS")

    summary = summarize_trace(trace)

    assert summary.search_count == 1
    assert summary.semantic_explore_count == 1
    assert summary.git_count == 1
