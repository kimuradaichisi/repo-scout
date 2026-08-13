from pathlib import Path

from reposcout.executors.read_file import FileReadExecutor
from reposcout.models import InvestigationQuery, QueryTool


def test_reads_requested_line_range(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("a\nb\nc\n", encoding="utf-8")

    query = InvestigationQuery(
        id="Q1",
        tool=QueryTool.READ,
        file="sample.py",
        start_line=2,
        end_line=3,
    )

    result = FileReadExecutor().execute(tmp_path, query)

    assert result.status == "PASS"
    assert result.evidence == "2:b\n3:c"
