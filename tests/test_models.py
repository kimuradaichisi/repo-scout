import pytest
from pydantic import ValidationError

from reposcout.models import InvestigationQuery, QueryTool


def test_rg_requires_pattern() -> None:
    with pytest.raises(ValidationError):
        InvestigationQuery(id="Q1", tool=QueryTool.RG)


def test_instruction_allows_ornith_query() -> None:
    query = InvestigationQuery(id="Q1", instruction="Find related tests")
    assert query.tool is None
    assert query.instruction == "Find related tests"
