"""Real executor -> EvidenceResult -> EvidenceContract source location traceability.

Regression coverage for the gap found in review: fixture-only tests (passing a
manually constructed EvidenceResult(source_locations=[...])) never exercised
whether the real executors populate source_locations at all. They didn't.
These tests run the actual executors against real files in a real git repo.
"""

import subprocess
from pathlib import Path

from reposcout.evidence import EvidenceWriter
from reposcout.executors.git_log import GitLogExecutor
from reposcout.executors.read_file import FileReadExecutor
from reposcout.executors.ripgrep import RipgrepExecutor
from reposcout.models import InvestigationPlan, InvestigationQuery, QueryTool


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _write_and_commit(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)


def test_real_ripgrep_execution_yields_source_location(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_and_commit(tmp_path, "src/a.py", "a\nb\ndef target():\n    pass\n")

    query = InvestigationQuery(id="Q1", tool=QueryTool.RG, pattern="def target")
    result = RipgrepExecutor().execute(tmp_path, query)

    assert result.status == "PASS"
    assert len(result.source_locations) == 1
    location = result.source_locations[0]
    assert (location.path, location.start_line, location.end_line) == ("src/a.py", 3, 3)


def test_real_ripgrep_multiple_matches_are_multiple_locations(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_and_commit(tmp_path, "src/a.py", "hit\nx\nhit\ny\nhit\n")

    query = InvestigationQuery(id="Q1", tool=QueryTool.RG, pattern="hit")
    result = RipgrepExecutor().execute(tmp_path, query)

    assert [(loc.path, loc.start_line, loc.end_line) for loc in result.source_locations] == [
        ("src/a.py", 1, 1),
        ("src/a.py", 3, 3),
        ("src/a.py", 5, 5),
    ]


def test_real_read_execution_yields_actual_range(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_and_commit(tmp_path, "src/a.py", "l1\nl2\nl3\nl4\nl5\n")

    query = InvestigationQuery(
        id="Q1", tool=QueryTool.READ, file="src/a.py", start_line=2, end_line=4
    )
    result = FileReadExecutor().execute(tmp_path, query)

    assert result.status == "PASS"
    assert len(result.source_locations) == 1
    location = result.source_locations[0]
    assert location.path == "src/a.py"
    assert location.start_line == 2
    assert location.end_line == 4
    assert location.content_hash is not None


def test_real_read_execution_truncated_by_eof_reports_actual_range(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_and_commit(tmp_path, "src/a.py", "l1\nl2\nl3\n")

    query = InvestigationQuery(
        id="Q1", tool=QueryTool.READ, file="src/a.py", start_line=2, end_line=100
    )
    result = FileReadExecutor().execute(tmp_path, query)

    assert result.source_locations[0].start_line == 2
    assert result.source_locations[0].end_line == 3


def test_real_git_log_execution_has_no_fabricated_source_location(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_and_commit(tmp_path, "src/a.py", "x\n")

    result = GitLogExecutor().execute(tmp_path, InvestigationQuery(id="Q1", tool=QueryTool.GIT_LOG))

    assert result.status == "PASS"
    assert result.evidence != ""
    assert result.source_locations == []


def test_contract_deduplicates_locations_from_real_ripgrep_execution(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_and_commit(tmp_path, "src/a.py", "dup\nother\ndup\n")

    plan = InvestigationPlan(
        goal="find dup",
        queries=[
            InvestigationQuery(id="Q1", tool=QueryTool.RG, pattern="dup", paths=["src/a.py"]),
            InvestigationQuery(id="Q2", tool=QueryTool.RG, pattern="dup", paths=["src/a.py"]),
        ],
    )
    results = [RipgrepExecutor().execute(tmp_path, query) for query in plan.queries]

    contract = EvidenceWriter().build_contract(plan, results)

    assert len(contract.query_evidence[0].source_locations) == 2
    assert len(contract.source_locations) == 2
