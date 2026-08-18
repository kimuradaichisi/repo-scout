"""Every ```bash smoketest block in the Claude Usage Policy actually runs.

Regression guard against docs/CLI drift: if a documented command's flags or
subcommand names stop matching the real CLI, this fails instead of silently
going stale.
"""

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "docs" / "claude_usage_policy.md"
_SMOKETEST_BLOCK = re.compile(r"```bash smoketest\n(.*?)```", re.DOTALL)


def _extract_smoketest_commands(text: str) -> list[str]:
    return [match.group(1).strip() for match in _SMOKETEST_BLOCK.finditer(text)]


def _init_target_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "src" / "reposcout").mkdir(parents=True)
    (root / "src" / "reposcout" / "models.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)


def test_policy_doc_has_smoketest_commands_for_every_documented_tool() -> None:
    commands = _extract_smoketest_commands(POLICY_PATH.read_text(encoding="utf-8"))

    joined = "\n".join(commands)
    assert "reposcout skeleton" in joined
    assert "reposcout query" in joined
    assert "reposcout investigate" in joined
    assert "reposcout pack" in joined
    assert "--trace-out" in joined


def test_every_smoketest_command_succeeds_against_a_real_repo(tmp_path: Path) -> None:
    target = tmp_path / "target-repo"
    target.mkdir()
    _init_target_repo(target)

    commands = _extract_smoketest_commands(POLICY_PATH.read_text(encoding="utf-8"))
    assert len(commands) >= 4  # skeleton, query, investigate, pack (trace variant included)

    for command in commands:
        resolved = command.replace("<target-repo>", str(target))
        completed = subprocess.run(
            ["bash", "-c", resolved],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, (
            f"command failed:\n{resolved}\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )


def test_investigate_smoketest_actually_produces_evidence_contract(tmp_path: Path) -> None:
    target = tmp_path / "target-repo"
    target.mkdir()
    _init_target_repo(target)
    commands = _extract_smoketest_commands(POLICY_PATH.read_text(encoding="utf-8"))
    command = next(c for c in commands if "reposcout investigate" in c and "--trace-out" not in c)

    subprocess.run(
        ["bash", "-c", command.replace("<target-repo>", str(target))],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )

    contract_path = Path("/tmp/reposcout-usage-policy-plan/run/evidence-contract.json")
    assert contract_path.is_file()
    assert json.loads(contract_path.read_text(encoding="utf-8"))["goal"] == "smoke test"


def test_trace_smoketest_actually_produces_investigation_trace(tmp_path: Path) -> None:
    target = tmp_path / "target-repo"
    target.mkdir()
    _init_target_repo(target)
    commands = _extract_smoketest_commands(POLICY_PATH.read_text(encoding="utf-8"))
    command = next(c for c in commands if "--trace-out" in c)

    subprocess.run(
        ["bash", "-c", command.replace("<target-repo>", str(target))],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )

    trace_path = Path("/tmp/reposcout-usage-policy-trace/trace.jsonl")
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["record_type"] == "trace"
    assert records[0]["investigation_id"] == "claude-session-example"
    assert records[-1]["record_type"] == "complete"
