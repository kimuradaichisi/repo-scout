import subprocess
from pathlib import Path

from reposcout.models import EvidenceResult, InvestigationQuery, QueryTool
from reposcout.runner import QueryRunner


class FakeOrnithWorker:
    """Records whether/how it was called; never touches a subprocess."""

    def __init__(self) -> None:
        self.calls: list[InvestigationQuery] = []

    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        self.calls.append(query)
        return EvidenceResult(query_id=query.id, status="PASS", executor="ornith", evidence="fake")


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "a.py").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)


def test_explicit_ripgrep_query_runs_as_before(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ornith = FakeOrnithWorker()
    query = InvestigationQuery(id="Q1", tool=QueryTool.RG, pattern="hello")

    result = QueryRunner(ornith_worker=ornith).execute(tmp_path, query)

    assert result.status == "PASS"
    assert result.executor == "ripgrep"
    assert ornith.calls == []


def test_explicit_read_query_runs_as_before(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ornith = FakeOrnithWorker()
    query = InvestigationQuery(id="Q1", tool=QueryTool.READ, file="a.py")

    result = QueryRunner(ornith_worker=ornith).execute(tmp_path, query)

    assert result.status == "PASS"
    assert result.executor == "file_read"
    assert ornith.calls == []


def test_explicit_git_log_query_runs_as_before(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ornith = FakeOrnithWorker()
    query = InvestigationQuery(id="Q1", tool=QueryTool.GIT_LOG)

    result = QueryRunner(ornith_worker=ornith).execute(tmp_path, query)

    assert result.status == "PASS"
    assert result.executor == "git_log"
    assert ornith.calls == []


def test_tool_unspecified_does_not_call_ornith(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ornith = FakeOrnithWorker()
    query = InvestigationQuery(id="Q1", instruction="Find related tests")

    QueryRunner(ornith_worker=ornith).execute(tmp_path, query)

    assert ornith.calls == []


def test_tool_unspecified_is_unresolved(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    query = InvestigationQuery(id="Q1", instruction="Find related tests")

    result = QueryRunner(ornith_worker=FakeOrnithWorker()).execute(tmp_path, query)

    assert result.status == "UNRESOLVED"
    assert result.evidence == ""
    assert result.error is not None


def test_deterministic_executor_failure_does_not_fall_back_to_ornith(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ornith = FakeOrnithWorker()
    query = InvestigationQuery(id="Q1", tool=QueryTool.READ, file="does_not_exist.py")

    result = QueryRunner(ornith_worker=ornith).execute(tmp_path, query)

    assert result.status == "ERROR"
    assert result.executor == "file_read"
    assert ornith.calls == []


def test_explicit_ornith_query_is_still_routed_to_ornith(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ornith = FakeOrnithWorker()
    query = InvestigationQuery(id="Q1", tool=QueryTool.ORNITH, instruction="Find related tests")

    result = QueryRunner(ornith_worker=ornith).execute(tmp_path, query)

    assert len(ornith.calls) == 1
    assert ornith.calls[0].id == "Q1"
    assert result.status == "PASS"
    assert result.executor == "ornith"
