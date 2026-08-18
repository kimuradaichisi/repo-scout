import subprocess
from pathlib import Path

from reposcout.skeleton import RepositorySkeleton


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _add(root: Path, relative: str, content: str = "x") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)


def test_lists_only_tracked_src_and_tests_unit_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _add(tmp_path, "src/reposcout/models.py")
    _add(tmp_path, "tests/unit/test_models.py")
    _add(tmp_path, "README.md")
    (tmp_path / "src/reposcout/untracked.py").write_text("x", encoding="utf-8")
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    files = RepositorySkeleton().list_files(tmp_path)

    assert files == ["src/reposcout/models.py", "tests/unit/test_models.py"]


def test_as_text_joins_with_newlines(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _add(tmp_path, "src/a.py")
    _add(tmp_path, "src/b.py")
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    assert RepositorySkeleton().as_text(tmp_path) == "src/a.py\nsrc/b.py"


def test_empty_when_no_tracked_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")

    assert RepositorySkeleton().list_files(tmp_path) == []
    assert RepositorySkeleton().as_text(tmp_path) == ""
