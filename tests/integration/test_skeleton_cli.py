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
