from pathlib import Path

from reposcout.models import EvidenceResult, InvestigationPlan, InvestigationQuery, QueryTool
from reposcout.runner import InvestigationRunner


class FakeQueryRunner:
    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        return EvidenceResult(
            query_id=query.id,
            status="PASS",
            executor="fake",
            evidence="raw evidence",
        )


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
    assert len(lines) == 3
    assert all('"investigation_id": "caller-id"' in line for line in lines)
    assert '"action": "read"' in lines[1]
    assert '"action": "stop"' in lines[2]
