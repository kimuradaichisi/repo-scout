"""CP8 Step 0-A — role-aware Write/Edit gate. Not scored, not a CP8 result.

Step 0 found that withholding Write/Edit from Main on the command line also
withheld them from the Sonnet Worker, because a subagent's usable tools are
the intersection of the CLI grant and its own declaration. Step 0-A moves the
distinction into a PreToolUse hook that can see who is calling, and checks
that the two halves actually come apart:

    Main   Write/Edit -> denied by role_gate.py    (no agent_id)
    Worker Write/Edit -> allowed by role_gate.py   (agent_type sonnet-worker)

The pre_worker_diff_empty gate is unchanged and still guards delegation, so
Config B ends up with two independent refusals rather than one. Both probes
write only under .cp8/, which the snapshot gitignores, so exercising writes
does not dirty the tree and the two gates never mask each other.
"""

import argparse
import json
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
    working_tree_status,
)
from cp8_hashes import environment_record, sha256_file
from cp8_permissions import config_b_allowed, config_b_disallowed
from cp8_step0_prompts import STEP0_PLAN_YAML
from cp8_step0a_checks import Step0AArtifacts, parse_role_log, run_checks, single_command_denials
from cp8_step0a_prompts import (
    MAIN_EDIT_TARGET,
    MAIN_EDIT_TARGET_BODY,
    MAIN_WRITE_TARGET,
    PROBE_DELEGATE_PROMPT,
    PROBE_MAIN_PROMPT,
    WORKER_WRITE_TARGET,
)
from cp8_transcript import load_events, tool_calls
from cp8_worker_metrics import delegation_observations
from run_comparison import MAIN_MODEL, count_repo_leaks

ROLE_LOG = ".cp8/role_gate.log"
PRE_WORKER_LOG = ".cp8/pre_worker_gate.log"
PLAN_PATH = ".cp8/step0-plan.yaml"


def _seed_scratch(snapshot: Path) -> None:
    """Lay down the throwaway files the probes act on, all inside .cp8/."""
    scratch = snapshot / ".cp8"
    scratch.mkdir(parents=True, exist_ok=True)
    (snapshot / PLAN_PATH).write_text(STEP0_PLAN_YAML, encoding="utf-8")
    (snapshot / MAIN_EDIT_TARGET).write_text(MAIN_EDIT_TARGET_BODY, encoding="utf-8")
    for stale in (MAIN_WRITE_TARGET, WORKER_WRITE_TARGET, ROLE_LOG, PRE_WORKER_LOG):
        (snapshot / stale).unlink(missing_ok=True)


def _read(snapshot: Path, relative: str) -> str:
    path = snapshot / relative
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _probe(prompt: str, label: str, snapshot: Path, run_dir: Path) -> tuple[ClaudeRun, Path]:
    transcript = run_dir / f"{label}.jsonl"
    run = run_claude(
        prompt,
        label=label,
        root=snapshot,
        transcript_path=transcript,
        model=MAIN_MODEL,
        allowed_tools=config_b_allowed(),
        disallowed_tools=config_b_disallowed(),
    )
    (run_dir / f"{label}-answer.md").write_text(run.final_text, encoding="utf-8")
    print(f"    {label}: exit={run.exit_code} out={run.output_tokens} {run.wall_seconds:.1f}s")
    return run, transcript


def _run_probes(snapshot: Path, run_dir: Path) -> dict[str, Any]:
    _seed_scratch(snapshot)
    edit_sha_before = sha256_file(snapshot / MAIN_EDIT_TARGET)
    main_run, main_transcript = _probe(
        PROBE_MAIN_PROMPT, "CP8-step0a-main-write", snapshot, run_dir
    )
    state = {
        "main_run": main_run,
        "main_transcript": main_transcript,
        "main_role_log": _read(snapshot, ROLE_LOG),
        "main_edit_sha_before": edit_sha_before,
        "main_edit_sha_after": sha256_file(snapshot / MAIN_EDIT_TARGET),
        "main_write_target_exists": (snapshot / MAIN_WRITE_TARGET).exists(),
    }

    reset_working_tree(snapshot)
    _seed_scratch(snapshot)
    delegate_run, delegate_transcript = _probe(
        PROBE_DELEGATE_PROMPT, "CP8-step0a-worker-write", snapshot, run_dir
    )
    state |= {
        "delegate_run": delegate_run,
        "delegate_transcript": delegate_transcript,
        "worker_role_log": _read(snapshot, ROLE_LOG),
        "pre_worker_log": _read(snapshot, PRE_WORKER_LOG),
        "worker_file_exists": (snapshot / WORKER_WRITE_TARGET).exists(),
        "worker_file_body": _read(snapshot, WORKER_WRITE_TARGET),
    }
    return state


def _artifacts(state: dict[str, Any], repo_root: Path) -> Step0AArtifacts:
    leaks = sum(
        count_repo_leaks(state[key], repo_root)
        for key in ("main_transcript", "delegate_transcript")
    )
    return Step0AArtifacts(
        main_events=load_events(state["main_transcript"]),
        delegate_events=load_events(state["delegate_transcript"]),
        main_role_log=parse_role_log(state["main_role_log"]),
        worker_role_log=parse_role_log(state["worker_role_log"]),
        pre_worker_log=state["pre_worker_log"],
        main_write_target_exists=state["main_write_target_exists"],
        main_edit_sha_before=state["main_edit_sha_before"],
        main_edit_sha_after=state["main_edit_sha_after"],
        worker_file_exists=state["worker_file_exists"],
        worker_file_body=state["worker_file_body"],
        leak_count=leaks,
    )


def _observed_agents(artifacts: Step0AArtifacts) -> list[dict[str, Any]]:
    records = artifacts.main_role_log + artifacts.worker_role_log
    return [
        {
            "decision": r.get("decision"),
            "tool_name": r.get("tool_name"),
            "agent_id": r.get("agent_id"),
            "agent_type": r.get("agent_type"),
            "target": r.get("target"),
            "payload_keys": r.get("payload_keys"),
        }
        for r in records
    ]


def _report(state: dict[str, Any], artifacts: Step0AArtifacts, snapshot: Path) -> dict[str, Any]:
    checks = run_checks(artifacts)
    nested = [c for c in tool_calls(artifacts.delegate_events) if c.is_nested]
    return {
        "variant": "cp8-step0a",
        "phase": "cp8-step0a-role-aware-write-gate",
        "scored": False,
        "main_model": MAIN_MODEL,
        "environment": environment_record(snapshot),
        "checks": [asdict(check) for check in checks],
        "all_checks_passed": all(check.passed for check in checks),
        "role_gate_log": _observed_agents(artifacts),
        "pre_worker_gate_log": artifacts.pre_worker_log.strip(),
        "worker_file_body": artifacts.worker_file_body,
        "worker_nested_tool_calls": sorted({c.name for c in nested}),
        "delegation": [asdict(c) for c in delegation_observations(artifacts.delegate_events)],
        "single_command_denials": single_command_denials(artifacts.main_events),
        "repo_root_leaks": artifacts.leak_count,
        "probes": {
            key: {
                "output_tokens": state[key].output_tokens,
                "cost_usd": round(state[key].cost_usd, 6),
                "elapsed_seconds": round(state[key].wall_seconds, 3),
                "permission_denials": len(state[key].permission_denials),
            }
            for key in ("main_run", "delegate_run")
        },
    }


def _print_checks(report: dict[str, Any]) -> None:
    print("\n--- Step 0-A checks ---")
    for check in report["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        print(f"  {check['letter']}. [{mark}] {check['title']}")
        print(f"        {check['detail']}")
    print(f"\nall_checks_passed: {report['all_checks_passed']}")
    print(f"single_command_denials: {report['single_command_denials'] or '(none)'}")


def _setup(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-cp8-step0a"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"RepoScout binary: {inject_reposcout_bin(repo_root)}")
    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-cp8"
    snapshot = prepare_snapshot(repo_root, snapshot_root / timestamp / "target")
    print(f"Snapshot: {snapshot}")

    isolate_environment(repo_root, snapshot)
    sync = sync_snapshot_env(snapshot)
    print(f"uv sync: exit={sync.returncode}")
    print(f"tree before probes: {working_tree_status(snapshot) or '(clean)'}")
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

    (run_dir / "cp8-step0a-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_checks(report)
    print(f"\nJSON: {run_dir / 'cp8-step0a-results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
