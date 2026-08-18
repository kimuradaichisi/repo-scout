import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pack_cli_produces_machine_readable_output(tmp_path: Path) -> None:
    request_file = tmp_path / "request.yaml"
    request_file.write_text(
        yaml.safe_dump(
            {
                "ranges": [
                    {"path": "src/reposcout/skeleton.py", "start_line": 1, "end_line": 5},
                    {"path": "src/reposcout/skeleton.py", "start_line": 4, "end_line": 10},
                ]
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "reposcout.cli",
            "pack",
            str(request_file),
            "--root",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["metrics"]["requested_ranges"] == 2
    assert payload["metrics"]["packed_ranges"] == 1
    assert payload["sources"][0]["path"] == "src/reposcout/skeleton.py"
    assert payload["sources"][0]["start_line"] == 1
    assert payload["sources"][0]["end_line"] == 10


def test_pack_cli_reports_untracked_path_as_json_error_not_traceback(tmp_path: Path) -> None:
    request_file = tmp_path / "request.yaml"
    request_file.write_text(
        yaml.safe_dump({"ranges": [{"path": "does/not/exist.py", "start_line": 1, "end_line": 1}]}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "reposcout.cli",
            "pack",
            str(request_file),
            "--root",
            str(REPO_ROOT),
        ],
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


def test_pack_cli_reports_invalid_request_shape_as_json_error_not_traceback(tmp_path: Path) -> None:
    request_file = tmp_path / "request.yaml"
    request_file.write_text(
        "ranges:\n  - path: src/a.py\n    start_line: 5\n    end_line: 1\n", encoding="utf-8"
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "reposcout.cli",
            "pack",
            str(request_file),
            "--root",
            str(REPO_ROOT),
        ],
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
