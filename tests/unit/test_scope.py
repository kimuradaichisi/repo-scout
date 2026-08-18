import subprocess
from pathlib import Path

from reposcout.pack import EvidencePackBuilder
from reposcout.scope import FileScopeMode, RepositoryFileScope


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _add(root: Path, relative: str, content: str = "x") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)


def _write(root: Path, relative: str, content: str = "x") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _mixed_repo(tmp_path: Path) -> Path:
    """tracked + untracked-not-ignored + ignored, spanning src and tests/unit."""
    _init_repo(tmp_path)
    _add(tmp_path, "src/reposcout/models.py")
    _add(tmp_path, "tests/unit/test_models.py")
    _write(tmp_path, ".gitignore", "src/reposcout/build_output.py\n")
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    _write(tmp_path, "src/reposcout/untracked_new.py")
    _write(tmp_path, "src/reposcout/build_output.py")
    return tmp_path


def test_tracked_only_reports_only_tracked_files(tmp_path: Path) -> None:
    root = _mixed_repo(tmp_path)

    files = RepositoryFileScope(FileScopeMode.TRACKED_ONLY).list_files(root)

    assert files == ["src/reposcout/models.py", "tests/unit/test_models.py"]


def test_workspace_includes_untracked_non_ignored(tmp_path: Path) -> None:
    root = _mixed_repo(tmp_path)

    files = RepositoryFileScope(FileScopeMode.WORKSPACE).list_files(root)

    assert "src/reposcout/untracked_new.py" in files


def test_workspace_excludes_gitignored(tmp_path: Path) -> None:
    root = _mixed_repo(tmp_path)

    files = RepositoryFileScope(FileScopeMode.WORKSPACE).list_files(root)

    assert "src/reposcout/build_output.py" not in files


def test_workspace_still_contains_tracked_files(tmp_path: Path) -> None:
    root = _mixed_repo(tmp_path)

    files = RepositoryFileScope(FileScopeMode.WORKSPACE).list_files(root)

    assert "src/reposcout/models.py" in files
    assert "tests/unit/test_models.py" in files


def test_default_mode_is_tracked_only(tmp_path: Path) -> None:
    root = _mixed_repo(tmp_path)

    assert RepositoryFileScope().list_files(root) == RepositoryFileScope(
        FileScopeMode.TRACKED_ONLY
    ).list_files(root)


def test_pack_reuses_the_same_scope_semantics_as_skeleton(tmp_path: Path) -> None:
    root = _mixed_repo(tmp_path)
    scope = RepositoryFileScope(FileScopeMode.WORKSPACE)

    assert scope.contains(root, "src/reposcout/untracked_new.py") is True

    builder = EvidencePackBuilder(scope=scope)
    from reposcout.models import SourceRange

    pack = builder.build(
        root, [SourceRange(path="src/reposcout/untracked_new.py", start_line=1, end_line=1)]
    )

    assert pack.sources[0].path == "src/reposcout/untracked_new.py"


def test_rejects_path_outside_repository(tmp_path: Path) -> None:
    root = _mixed_repo(tmp_path)

    assert RepositoryFileScope(FileScopeMode.WORKSPACE).contains(root, "../../etc/passwd") is False
    assert (
        RepositoryFileScope(FileScopeMode.TRACKED_ONLY).contains(root, "../../etc/passwd") is False
    )
