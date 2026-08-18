import pytest
from pydantic import ValidationError

from reposcout.models import InvestigationContract


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "goal": "Find who consumes EvidenceWriter",
        "questions": ["Where is EvidenceWriter defined?"],
        "known_facts": ["EvidenceWriter lives in src/reposcout/evidence.py"],
        "target_hints": ["EvidenceWriter"],
        "constraints": ["do not read docs/"],
        "stop_conditions": ["all questions answered"],
    }
    kwargs.update(overrides)
    return kwargs


def test_builds_a_valid_contract() -> None:
    contract = InvestigationContract(**_valid_kwargs())

    assert contract.goal == "Find who consumes EvidenceWriter"


def test_rejects_empty_goal() -> None:
    with pytest.raises(ValidationError):
        InvestigationContract(**_valid_kwargs(goal=""))


def test_rejects_empty_questions() -> None:
    with pytest.raises(ValidationError):
        InvestigationContract(**_valid_kwargs(questions=[]))


def test_rejects_empty_stop_conditions() -> None:
    with pytest.raises(ValidationError):
        InvestigationContract(**_valid_kwargs(stop_conditions=[]))


def test_known_facts_may_be_empty() -> None:
    contract = InvestigationContract(**_valid_kwargs(known_facts=[]))

    assert contract.known_facts == []


def test_target_hints_may_be_empty() -> None:
    contract = InvestigationContract(**_valid_kwargs(target_hints=[]))

    assert contract.target_hints == []


def test_constraints_may_be_empty() -> None:
    contract = InvestigationContract(**_valid_kwargs(constraints=[]))

    assert contract.constraints == []


def test_each_collection_retains_its_given_values() -> None:
    contract = InvestigationContract(
        **_valid_kwargs(
            questions=["Q1", "Q2"],
            known_facts=["F1"],
            target_hints=["H1", "H2", "H3"],
            constraints=["C1"],
            stop_conditions=["S1", "S2"],
        )
    )

    assert contract.questions == ["Q1", "Q2"]
    assert contract.known_facts == ["F1"]
    assert contract.target_hints == ["H1", "H2", "H3"]
    assert contract.constraints == ["C1"]
    assert contract.stop_conditions == ["S1", "S2"]
