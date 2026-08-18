from pathlib import Path

from reposcout.models import EvidenceResult, InvestigationPlan, InvestigationQuery, QueryTool
from reposcout.runner import InvestigationRunner, QueryRunner


class FakeQueryRunner:
    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        return EvidenceResult(
            query_id=query.id,
            status="PASS",
            executor="fake",
            evidence="raw evidence",
        )


class FakeOrnithWorker:
    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        return EvidenceResult(query_id=query.id, status="PASS", executor="ornith", evidence="fake")


def test_investigation_writes_evidence_contract_without_removing_raw_pack(tmp_path: Path) -> None:
    plan = InvestigationPlan(
        goal="Test contract",
        queries=[InvestigationQuery(id="Q1", instruction="Read source")],
    )

    results = InvestigationRunner(query_runner=FakeQueryRunner()).execute(
        root=tmp_path,
        plan=plan,
        run_dir=tmp_path / "run",
    )

    assert results[0].evidence == "raw evidence"
    assert (tmp_path / "run" / "evidence.md").is_file()
    assert (tmp_path / "run" / "evidence-contract.json").is_file()


def test_no_trace_out_leaves_no_trace_file(tmp_path: Path) -> None:
    plan = InvestigationPlan(
        goal="No trace",
        queries=[InvestigationQuery(id="Q1", instruction="Read source")],
    )

    InvestigationRunner(query_runner=FakeQueryRunner()).execute(
        root=tmp_path,
        plan=plan,
        run_dir=tmp_path / "run",
    )

    assert not (tmp_path / ".reposcout").exists()
    assert list(tmp_path.glob("**/*.jsonl")) == []


def test_investigation_trace_records_query_and_stop_with_same_id(tmp_path: Path) -> None:
    plan = InvestigationPlan(
        goal="Trace execution",
        queries=[InvestigationQuery(id="Q1", tool=QueryTool.READ, file="source.py")],
    )
    trace_path = tmp_path / "traces" / "investigation.jsonl"

    InvestigationRunner(query_runner=FakeQueryRunner()).execute(
        root=tmp_path,
        plan=plan,
        run_dir=tmp_path / "run",
        investigation_id="caller-id",
        trace_out=trace_path,
    )

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert all('"investigation_id": "caller-id"' in line for line in lines)
    assert '"record_type": "trace"' in lines[0]
    assert '"action": "read"' in lines[1]
    assert '"action": "stop"' in lines[2]
    assert '"record_type": "complete"' in lines[3]


def test_trace_file_has_header_and_first_step_before_investigation_finishes(
    tmp_path: Path,
) -> None:
    """Regression: the old writer buffered every step and wrote once at the
    end, so a crash mid-investigation produced zero trace output. Simulate
    the mid-run state by running just far enough to see the first step land,
    without waiting for execute() to return."""
    plan = InvestigationPlan(
        goal="Partial",
        queries=[
            InvestigationQuery(id="Q1", tool=QueryTool.READ, file="a.py"),
            InvestigationQuery(id="Q2", tool=QueryTool.READ, file="b.py"),
        ],
    )
    trace_path = tmp_path / "trace.jsonl"
    runner = InvestigationRunner(query_runner=FakeQueryRunner())
    trace, writer = runner._start_trace("inv-partial", trace_path)
    assert trace_path.is_file()

    result = FakeQueryRunner().execute(tmp_path, plan.queries[0])
    step = runner._record_query(trace, plan.queries[0], result, 0.0)
    writer.append_step(trace, step)

    lines_after_one_step = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines_after_one_step) == 2
    assert not any('"record_type": "complete"' in line for line in lines_after_one_step)


def test_explicit_ornith_query_is_traced_as_semantic_explore_not_search(tmp_path: Path) -> None:
    plan = InvestigationPlan(
        goal="Semantic",
        queries=[InvestigationQuery(id="Q1", tool=QueryTool.ORNITH, instruction="find usage")],
    )
    trace_path = tmp_path / "trace.jsonl"

    InvestigationRunner(query_runner=QueryRunner(ornith_worker=FakeOrnithWorker())).execute(
        root=tmp_path,
        plan=plan,
        run_dir=tmp_path / "run",
        trace_out=trace_path,
    )

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert '"action": "semantic_explore"' in lines[1]
    assert '"action": "search"' not in lines[1]
