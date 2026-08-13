from pathlib import Path

from reposcout.evidence import EvidenceWriter
from reposcout.models import EvidenceResult, InvestigationPlan, InvestigationQuery


def test_writes_evidence_pack(tmp_path: Path) -> None:
    plan = InvestigationPlan(
        goal="Find usage",
        queries=[InvestigationQuery(id="Q1", instruction="Search usage")],
    )
    results = [
        EvidenceResult(
            query_id="Q1",
            status="PASS",
            executor="ornith",
            evidence="sample.py:10",
        )
    ]

    EvidenceWriter().write_pack(tmp_path, plan, results)

    content = (tmp_path / "evidence.md").read_text(encoding="utf-8")
    assert "Find usage" in content
    assert "sample.py:10" in content
