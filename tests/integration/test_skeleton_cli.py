import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_skeleton_cli_matches_git_ls_files() -> None:
    cli = subprocess.run(
        [sys.executable, "-m", "reposcout.cli", "skeleton", "--root", str(REPO_ROOT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    expected = subprocess.run(
        ["git", "ls-files", "src", "tests/unit"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert cli.stdout.strip().splitlines() == expected.stdout.strip().splitlines()
    assert "src/reposcout/models.py" in cli.stdout
    assert "README.md" not in cli.stdout


def test_skeleton_cli_reports_git_failure_as_json_error_not_traceback(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "reposcout.cli", "skeleton", "--root", str(tmp_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "Traceback" not in completed.stdout
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert "error" in payload


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def test_skeleton_cli_scope_workspace_includes_untracked_non_ignored(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/tracked.py").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "src/tracked.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / "src/untracked.py").write_text("x", encoding="utf-8")

    tracked_only = subprocess.run(
        [sys.executable, "-m", "reposcout.cli", "skeleton", "--root", str(tmp_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    workspace = subprocess.run(
        [
            sys.executable,
            "-m",
            "reposcout.cli",
            "skeleton",
            "--root",
            str(tmp_path),
            "--scope",
            "workspace",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "src/untracked.py" not in tracked_only.stdout
    assert "src/untracked.py" in workspace.stdout
    assert "src/tracked.py" in tracked_only.stdout
    assert "src/tracked.py" in workspace.stdout
