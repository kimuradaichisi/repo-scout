"""CP8 Step 0 — infrastructure smoke test. Not scored, and not a CP8 result.

Step 0 asks whether the apparatus Config B needs actually exists in this
Claude Code build: whether a custom Sonnet subagent can be reached from a
headless run, whether its model and its tool calls are observable afterwards,
whether the delegation gate really refuses a dirty tree, and whether Main's
Bash allowlist is both sufficient for its work and closed to writing.

Three throwaway probes, none of which reads anything T1/T2/T3 touches:

    A  Main-side infrastructure: ./scout, the gates, the write escapes
    B  delegation on a clean tree      -- the hook must allow
    C  delegation on a dirty tree      -- the hook must deny

A failing check is a finding, not something to route around: the run reports
it and stops, because the design is what would need to change.
"""

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass, field
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
from cp8_step0_checks import Step0Artifacts, run_checks
from cp8_step0_prompts import PROBE_A_PROMPT, PROBE_B_PROMPT, PROBE_C_PROMPT, STEP0_PLAN_YAML
from cp8_transcript import load_events
from cp8_worker_metrics import delegation_observations, model_separation, worker_metrics
from run_comparison import MAIN_MODEL, count_repo_leaks

GATE_LOG = ".cp8/pre_worker_gate.log"
PLAN_PATH = ".cp8/step0-plan.yaml"
SCOUT_EVIDENCE = ".scout/step0-plan/evidence.md"


@dataclass
class Probe:
    label: str
    run: ClaudeRun
    events: list[dict[str, Any]] = field(default_factory=list)
    transcript: Path = Path()


def _prepare(snapshot: Path) -> None:
    plan = snapshot / PLAN_PATH
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(STEP0_PLAN_YAML, encoding="utf-8")


def _clear_gate_log(snapshot: Path) -> None:
    log = snapshot / GATE_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")


def _gate_log(snapshot: Path) -> str:
    log = snapshot / GATE_LOG
    return log.read_text(encoding="utf-8") if log.exists() else ""


def _dirty_tree(snapshot: Path) -> None:
    """Make the tree dirty in a way the gate must notice."""
    readme = snapshot / "README.md"
    body = readme.read_text(encoding="utf-8")
    readme.write_text(f"{body}\nstep0 dirty marker\n", encoding="utf-8")


def _probe(prompt: str, label: str, snapshot: Path, run_dir: Path) -> Probe:
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
    return Probe(label=label, run=run, events=load_events(transcript), transcript=transcript)


def _observations(probe_b: list[dict[str, Any]]) -> dict[str, Any]:
    delegations = delegation_observations(probe_b)
    metrics = worker_metrics(probe_b, frozenset())
    return {
        "delegation_tool_names_observed": sorted({call.tool_name for call in delegations}),
        "subagent_types_observed": sorted({call.subagent_type or "?" for call in delegations}),
        "model_separation": model_separation(probe_b),
        "worker_internal_tool_calls": metrics.worker_tool_calls,
        "worker_internal_calls_observable": metrics.nested_calls_observed,
    }


def _run_probes(snapshot: Path, run_dir: Path) -> tuple[Probe, Probe, Probe, dict[str, Any]]:
    _clear_gate_log(snapshot)
    readme_before = sha256_file(snapshot / "README.md")
    probe_a = _probe(PROBE_A_PROMPT, "CP8-step0-a-main-infra", snapshot, run_dir)
    readme_after = sha256_file(snapshot / "README.md")

    reset_working_tree(snapshot)
    _clear_gate_log(snapshot)
    probe_b = _probe(PROBE_B_PROMPT, "CP8-step0-b-delegate-clean", snapshot, run_dir)
    gate_log_b = _gate_log(snapshot)

    reset_working_tree(snapshot)
    _clear_gate_log(snapshot)
    _dirty_tree(snapshot)
    probe_c = _probe(PROBE_C_PROMPT, "CP8-step0-c-delegate-dirty", snapshot, run_dir)
    gate_log_c = _gate_log(snapshot)
    reset_working_tree(snapshot)

    state = {
        "readme_sha_before": readme_before,
        "readme_sha_after": readme_after,
        "gate_log_b": gate_log_b,
        "gate_log_c": gate_log_c,
    }
    return probe_a, probe_b, probe_c, state


def _build_artifacts(
    probes: tuple[Probe, Probe, Probe], state: dict[str, Any], snapshot: Path, repo_root: Path
) -> Step0Artifacts:
    probe_a, probe_b, probe_c = probes
    leaks = sum(count_repo_leaks(probe.transcript, repo_root) for probe in probes)
    return Step0Artifacts(
        probe_a=probe_a.events,
        probe_b=probe_b.events,
        probe_c=probe_c.events,
        environment=environment_record(snapshot),
        leak_count=leaks,
        scout_evidence_exists=(snapshot / SCOUT_EVIDENCE).exists(),
        **state,
    )


def _report(probes: tuple[Probe, Probe, Probe], artifacts: Step0Artifacts) -> dict[str, Any]:
    checks = run_checks(artifacts)
    return {
        "variant": "cp8-step0",
        "phase": "cp8-step0-infrastructure-smoke-test",
        "scored": False,
        "main_model": MAIN_MODEL,
        "environment": artifacts.environment,
        "checks": [asdict(check) for check in checks],
        "all_checks_passed": all(check.passed for check in checks),
        "observations": _observations(artifacts.probe_b),
        "gate_log_clean_tree": artifacts.gate_log_b.strip(),
        "gate_log_dirty_tree": artifacts.gate_log_c.strip(),
        "repo_root_leaks": artifacts.leak_count,
        "probes": {
            probe.label: {
                "exit_code": probe.run.exit_code,
                "input_tokens": probe.run.total_input_tokens,
                "output_tokens": probe.run.output_tokens,
                "cost_usd": round(probe.run.cost_usd, 6),
                "elapsed_seconds": round(probe.run.wall_seconds, 3),
                "permission_denials": probe.run.permission_denials,
            }
            for probe in probes
        },
    }


def _print_checks(report: dict[str, Any]) -> None:
    print("\n--- Step 0 checks ---")
    for check in report["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        print(f"  {check['number']:>2}. [{mark}] {check['title']}")
        print(f"        {check['detail']}")
    print(f"\nall_checks_passed: {report['all_checks_passed']}")


def _setup(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """Build the snapshot, install the fixed conditions, and seal the environment."""
    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-cp8-step0"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"RepoScout binary: {inject_reposcout_bin(repo_root)}")
    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-cp8"
    snapshot = prepare_snapshot(repo_root, snapshot_root / timestamp / "target")
    print(f"Snapshot: {snapshot}")

    isolate_environment(repo_root, snapshot)
    sync = sync_snapshot_env(snapshot)
    print(f"uv sync: exit={sync.returncode} {sync.stderr.strip().splitlines()[-1:] or ''}")
    _prepare(snapshot)
    print(f"tree before probes: {working_tree_status(snapshot) or '(clean)'}")
    return repo_root, snapshot, run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    repo_root, snapshot, run_dir = _setup(parser.parse_args())

    probe_a, probe_b, probe_c, state = _run_probes(snapshot, run_dir)
    probes = (probe_a, probe_b, probe_c)
    artifacts = _build_artifacts(probes, state, snapshot, repo_root)
    report = _report(probes, artifacts)

    (run_dir / "cp8-step0-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_checks(report)
    print(f"\nJSON: {run_dir / 'cp8-step0-results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
