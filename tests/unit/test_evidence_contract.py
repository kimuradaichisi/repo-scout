import json

from reposcout.evidence import EvidenceWriter
from reposcout.models import (
    EvidencePack,
    EvidenceResult,
    InvestigationPlan,
    InvestigationQuery,
    PackedSource,
    PackMetrics,
    SourceLocation,
)


def test_build_contract_preserves_raw_queries_and_deduplicates_locations() -> None:
    plan = InvestigationPlan(
        goal="Find usage",
        queries=[
            InvestigationQuery(id="Q1", instruction="Search usage"),
            InvestigationQuery(id="Q2", instruction="Read usage"),
        ],
    )
    location = SourceLocation(path="src/a.py", start_line=2, end_line=4)
    results = [
        EvidenceResult(
            query_id="Q1",
            status="PASS",
            executor="ripgrep",
            evidence="raw: FACTS are not inferred",
            source_locations=[location],
        ),
        EvidenceResult(
            query_id="Q2",
            status="PASS",
            executor="file_read",
            evidence="raw relation-like text",
            source_locations=[location, SourceLocation(path="src/b.py", start_line=1, end_line=1)],
        ),
    ]

    contract = EvidenceWriter().build_contract(plan, results)

    assert contract.goal == "Find usage"
    assert [item.query_id for item in contract.query_evidence] == ["Q1", "Q2"]
    assert contract.query_evidence[0].evidence == "raw: FACTS are not inferred"
    assert contract.query_evidence[0].executor == "ripgrep"
    assert contract.query_evidence[0].status == "PASS"
    assert [(item.path, item.start_line) for item in contract.source_locations] == [
        ("src/a.py", 2),
        ("src/b.py", 1),
    ]
    assert contract.unknown == []


def test_build_contract_keeps_unresolved_and_error_as_unknown() -> None:
    plan = InvestigationPlan(
        goal="Investigate",
        queries=[
            InvestigationQuery(id="Q1", instruction="Unknown"),
            InvestigationQuery(id="Q2", instruction="Broken"),
        ],
    )
    results = [
        EvidenceResult(query_id="Q1", status="UNRESOLVED", executor="none"),
        EvidenceResult(query_id="Q2", status="ERROR", executor="read", error="missing"),
    ]

    contract = EvidenceWriter().build_contract(plan, results)

    assert [(item.query_id, item.status, item.reason) for item in contract.unknown] == [
        ("Q1", "UNRESOLVED", "status=UNRESOLVED"),
        ("Q2", "ERROR", "missing"),
    ]


def test_build_contract_keeps_packed_hash_and_round_trips(tmp_path) -> None:
    plan = InvestigationPlan(
        goal="Pack source",
        queries=[InvestigationQuery(id="Q1", instruction="Read source")],
    )
    packed = EvidencePack(
        sources=[
            PackedSource(
                path="src/a.py",
                start_line=1,
                end_line=2,
                content="1:x\n2:y",
                sha256="abc123",
            )
        ],
        metrics=PackMetrics(
            requested_ranges=1,
            packed_ranges=1,
            requested_source_bytes=7,
            packed_source_bytes=7,
            duplicate_or_overlap_bytes_eliminated=0,
            unique_paths=1,
            pack_chars=7,
        ),
    )

    writer = EvidenceWriter()
    contract = writer.build_contract(
        plan,
        [EvidenceResult(query_id="Q1", status="PASS", executor="pack")],
        packed,
    )
    writer.write_contract(tmp_path, contract)
    loaded = json.loads((tmp_path / "evidence-contract.json").read_text(encoding="utf-8"))

    assert contract.source_locations[0].content_hash == "abc123"
    assert type(contract).model_validate(loaded) == contract


def test_partial_results_still_build_contract() -> None:
    plan = InvestigationPlan(
        goal="Partial",
        queries=[InvestigationQuery(id="Q1", instruction="Only one")],
    )

    contract = EvidenceWriter().build_contract(
        plan,
        [EvidenceResult(query_id="Q1", status="PASS", executor="read")],
    )

    assert len(contract.query_evidence) == 1
