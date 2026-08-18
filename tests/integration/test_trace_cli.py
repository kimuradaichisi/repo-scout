import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_investigate_cli_writes_opt_in_trace(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "goal: trace\nqueries:\n  - id: Q1\n    tool: read\n    file: source.py\n",
        encoding="utf-8",
    )
    trace = tmp_path / "trace.jsonl"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "reposcout.cli",
            "investigate",
            str(plan),
            "--root",
            str(tmp_path),
            "--trace-out",
            str(trace),
            "--investigation-id",
            "cli-id",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 3
    assert {record["investigation_id"] for record in records} == {"cli-id"}
