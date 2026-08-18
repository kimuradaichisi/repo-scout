"""CP8 Step 0-B — env-based role gate smoke test. Not scored, not a CP8 result.

Re-validates the role gate's ALLOW/DENY matrix after moving its control
condition from a mutable marker file (.cp8/active-config, writable by the
Sonnet Worker itself) to CP8_ACTIVE_CONFIG, an environment variable the
harness sets before the `claude` process starts and clears immediately after
(cp8_step1_runtime.run_main). Three throwaway probes:

    A  CP8_ACTIVE_CONFIG=config_a  -- Main Write/Edit must succeed
    B  CP8_ACTIVE_CONFIG=config_b  -- Main denied, sonnet-worker allowed,
                                       an unrecognised subagent denied
    C  CP8_ACTIVE_CONFIG unset     -- fails closed to config_b's denial

None of the three touches T1/T2/T3.
"""

import argparse
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_metrics import ClaudeRun, run_claude
from cp8_fixtures import (
    inject_reposcout_bin,
    isolate_environment,
    prepare_snapshot,
    reset_working_tree,
    sync_snapshot_env,
)
from cp8_hashes import environment_record, sha256_file
from cp8_permissions import config_b_allowed, config_b_disallowed
from cp8_step0b_checks import Step0BArtifacts, parse_role_log, run_checks
from cp8_step0b_prompts import (
    CONFIG_A_EDIT_BODY,
    CONFIG_A_EDIT_TARGET,
    CONFIG_A_WRITE_TARGET,
    CONFIG_B_MAIN_EDIT_BODY,
    CONFIG_B_MAIN_EDIT_TARGET,
    CONFIG_B_MAIN_WRITE_TARGET,
    CONFIG_B_UNKNOWN_TARGET,
    CONFIG_B_WORKER_TARGET,
    PROBE_CONFIG_A_PROMPT,
    PROBE_CONFIG_B_PROMPT,
    PROBE_UNSET_PROMPT,
    UNSET_WRITE_TARGET,
)
from run_comparison import MAIN_MODEL, count_repo_leaks

ROLE_LOG = ".cp8/role_gate.log"
ACTIVE_CONFIG_ENV = "CP8_ACTIVE_CONFIG"


def _read(snapshot: Path, relative: str) -> str:
    path = snapshot / relative
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _seed(snapshot: Path) -> None:
    (snapshot / ".cp8").mkdir(parents=True, exist_ok=True)
    (snapshot / CONFIG_A_EDIT_TARGET).write_text(CONFIG_A_EDIT_BODY, encoding="utf-8")
    (snapshot / CONFIG_B_MAIN_EDIT_TARGET).write_text(CONFIG_B_MAIN_EDIT_BODY, encoding="utf-8")
    for stale in (CONFIG_A_WRITE_TARGET, ROLE_LOG):
        (snapshot / stale).unlink(missing_ok=True)


def _probe(
    prompt: str, label: str, snapshot: Path, run_dir: Path, env_value: str | None
) -> tuple[ClaudeRun, Path]:
    transcript = run_dir / f"{label}.jsonl"
    if env_value is None:
        os.environ.pop(ACTIVE_CONFIG_ENV, None)
    else:
        os.environ[ACTIVE_CONFIG_ENV] = env_value
    try:
        run = run_claude(
            prompt,
            label=label,
            root=snapshot,
            transcript_path=transcript,
            model=MAIN_MODEL,
            allowed_tools=config_b_allowed(),
            disallowed_tools=config_b_disallowed(),
        )
    finally:
        os.environ.pop(ACTIVE_CONFIG_ENV, None)
    (run_dir / f"{label}-answer.md").write_text(run.final_text, encoding="utf-8")
    print(f"    {label}: exit={run.exit_code} out={run.output_tokens} {run.wall_seconds:.1f}s")
    return run, transcript


def _probe_config_a(snapshot: Path, run_dir: Path) -> dict[str, Any]:
    reset_working_tree(snapshot)
    _seed(snapshot)
    edit_before = sha256_file(snapshot / CONFIG_A_EDIT_TARGET)
    run, transcript = _probe(
        PROBE_CONFIG_A_PROMPT, "CP8-step0b-config-a", snapshot, run_dir, "config_a"
    )
    return {
        "run": run,
        "transcript": transcript,
        "role_log": _read(snapshot, ROLE_LOG),
        "write_exists": (snapshot / CONFIG_A_WRITE_TARGET).exists(),
        "edit_sha_before": edit_before,
        "edit_sha_after": sha256_file(snapshot / CONFIG_A_EDIT_TARGET),
    }


def _probe_config_b(snapshot: Path, run_dir: Path) -> dict[str, Any]:
    reset_working_tree(snapshot)
    _seed(snapshot)
    edit_before = sha256_file(snapshot / CONFIG_B_MAIN_EDIT_TARGET)
    run, transcript = _probe(
        PROBE_CONFIG_B_PROMPT, "CP8-step0b-config-b", snapshot, run_dir, "config_b"
    )
    return {
        "run": run,
        "transcript": transcript,
        "role_log": _read(snapshot, ROLE_LOG),
        "main_write_exists": (snapshot / CONFIG_B_MAIN_WRITE_TARGET).exists(),
        "main_edit_sha_before": edit_before,
        "main_edit_sha_after": sha256_file(snapshot / CONFIG_B_MAIN_EDIT_TARGET),
        "worker_file_exists": (snapshot / CONFIG_B_WORKER_TARGET).exists(),
        "worker_file_body": _read(snapshot, CONFIG_B_WORKER_TARGET),
        "unknown_file_exists": (snapshot / CONFIG_B_UNKNOWN_TARGET).exists(),
    }


def _probe_unset(snapshot: Path, run_dir: Path) -> dict[str, Any]:
    reset_working_tree(snapshot)
    _seed(snapshot)
    run, transcript = _probe(PROBE_UNSET_PROMPT, "CP8-step0b-unset", snapshot, run_dir, None)
    return {
        "run": run,
        "transcript": transcript,
        "role_log": _read(snapshot, ROLE_LOG),
        "write_exists": (snapshot / UNSET_WRITE_TARGET).exists(),
    }


def _run_probes(snapshot: Path, run_dir: Path) -> dict[str, Any]:
    state = {
        "a": _probe_config_a(snapshot, run_dir),
        "b": _probe_config_b(snapshot, run_dir),
        "c": _probe_unset(snapshot, run_dir),
    }
    reset_working_tree(snapshot)
    return state


def _artifacts(state: dict[str, Any], repo_root: Path) -> Step0BArtifacts:
    leaks = sum(count_repo_leaks(state[k]["transcript"], repo_root) for k in ("a", "b", "c"))
    a, b, c = state["a"], state["b"], state["c"]
    return Step0BArtifacts(
        config_a_role_log=parse_role_log(a["role_log"]),
        config_a_write_exists=a["write_exists"],
        config_a_edit_sha_before=a["edit_sha_before"],
        config_a_edit_sha_after=a["edit_sha_after"],
        config_b_role_log=parse_role_log(b["role_log"]),
        config_b_main_write_exists=b["main_write_exists"],
        config_b_main_edit_sha_before=b["main_edit_sha_before"],
        config_b_main_edit_sha_after=b["main_edit_sha_after"],
        config_b_worker_file_exists=b["worker_file_exists"],
        config_b_worker_file_body=b["worker_file_body"],
        config_b_unknown_file_exists=b["unknown_file_exists"],
        unset_role_log=parse_role_log(c["role_log"]),
        unset_write_exists=c["write_exists"],
        leak_count=leaks,
    )


def _report(state: dict[str, Any], artifacts: Step0BArtifacts, snapshot: Path) -> dict[str, Any]:
    checks = run_checks(artifacts)
    return {
        "variant": "cp8-step0b",
        "phase": "cp8-step0b-env-based-role-gate",
        "scored": False,
        "main_model": MAIN_MODEL,
        "environment": environment_record(snapshot),
        "checks": [asdict(check) for check in checks],
        "all_checks_passed": all(check.passed for check in checks),
        "repo_root_leaks": artifacts.leak_count,
        "probes": {
            key: {
                "output_tokens": state[key]["run"].output_tokens,
                "cost_usd": round(state[key]["run"].cost_usd, 6),
                "elapsed_seconds": round(state[key]["run"].wall_seconds, 3),
            }
            for key in ("a", "b", "c")
        },
    }


def _print_checks(report: dict[str, Any]) -> None:
    print("\n--- Step 0-B checks ---")
    for check in report["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        print(f"  {check['number']}. [{mark}] {check['title']}")
        print(f"        {check['detail']}")
    print(f"\nall_checks_passed: {report['all_checks_passed']}")


def _setup(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-cp8-step0b"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"RepoScout binary: {inject_reposcout_bin(repo_root)}")
    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-cp8"
    snapshot = prepare_snapshot(repo_root, snapshot_root / timestamp / "target")
    print(f"Snapshot: {snapshot}")
    isolate_environment(repo_root, snapshot)
    sync = sync_snapshot_env(snapshot)
    print(f"uv sync: exit={sync.returncode}")
    return repo_root, snapshot, run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    repo_root, snapshot, run_dir = _setup(parser.parse_args())

    state = _run_probes(snapshot, run_dir)
    artifacts = _artifacts(state, repo_root)
    report = _report(state, artifacts, snapshot)

    (run_dir / "cp8-step0b-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_checks(report)
    print(f"\nJSON: {run_dir / 'cp8-step0b-results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
