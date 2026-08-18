"""Verify cp9_telemetry against real transcripts. No model calls.

The inputs are CP8 Step 1's saved transcripts, read only. Using them is what
makes this a verification rather than a restatement: the expected values below
were read out of those files by hand first, so a passing check means the
extractor agrees with the transcript, not with itself.

The phase-sum check is the load-bearing one. Streamed assistant rows repeat a
request several times with usage that is still settling, so summing them
naively double-counts and summing the wrong row under-counts. Requiring the
two phases to add up to the run's own aggregate modelUsage is what proves the
per-request dedup is right -- and it is exactly the property that fails for
output tokens, which is why cp9_telemetry refuses to report those per phase.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cp8_transcript import load_events, model_usage
from cp9_telemetry import (
    DECISION_PHASE,
    IMPLEMENTATION_PHASE,
    WRITE_TOOLS,
    delegation_records,
    denial_counts,
    main_phase_boundary_tools,
    phase_totals,
)

CP8_RUN_DIR = "results/20260816-193324-cp8-step1"

# Read directly out of the transcripts before this module was written.
EXPECTED_DELEGATIONS = {
    "CP8-step1-config_b-t1_ripgrep_tests": {"tool_use_count": 42, "duration_ms": 149584},
    "CP8-step1-config_b-t2_git_log_tests": {"tool_use_count": 11, "duration_ms": 45491},
    "CP8-step1-config_b-t3_injectable_context": {"tool_use_count": 19, "duration_ms": 74852},
}
EXPECTED_WORKER_DENIALS = {
    "CP8-step1-config_b-t1_ripgrep_tests": 26,
    "CP8-step1-config_b-t2_git_log_tests": 1,
    "CP8-step1-config_b-t3_injectable_context": 1,
}
CONFIG_A_LABELS = (
    "CP8-step1-config_a-t1_ripgrep_tests",
    "CP8-step1-config_a-t2_git_log_tests",
    "CP8-step1-config_a-t3_injectable_context",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _events(run_dir: Path, label: str) -> list[dict[str, Any]]:
    return load_events(run_dir / f"{label}.jsonl")


def _opus_input_cache(events: list[dict[str, Any]]) -> int:
    entry = model_usage(events).get("claude-opus-5", {})
    return sum(
        int(entry.get(key, 0) or 0)
        for key in ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
    )


def check_delegation_fields(run_dir: Path) -> CheckResult:
    problems = []
    for label, expected in EXPECTED_DELEGATIONS.items():
        records = delegation_records(_events(run_dir, label))
        if len(records) != 1:
            problems.append(f"{label}: {len(records)} delegation records")
            continue
        record = records[0]
        if record["agent_type"] != "sonnet-worker":
            problems.append(f"{label}: agent_type={record['agent_type']}")
        if record["resolved_model"] != "claude-sonnet-5":
            problems.append(f"{label}: resolved_model={record['resolved_model']}")
        for key, value in expected.items():
            if record[key] != value:
                problems.append(f"{label}: {key}={record[key]} expected {value}")
    return CheckResult("delegation_fields_match_transcript", not problems, f"{problems or 'ok'}")


def check_tool_stats_present(run_dir: Path) -> CheckResult:
    required = {"readCount", "searchCount", "bashCount", "editFileCount", "linesAdded"}
    problems = []
    for label in EXPECTED_DELEGATIONS:
        stats = set(delegation_records(_events(run_dir, label))[0]["tool_stats"])
        if not required <= stats:
            problems.append(f"{label}: missing {sorted(required - stats)}")
    return CheckResult("tool_stats_structured", not problems, f"{problems or 'ok'}")


def check_denial_attribution(run_dir: Path) -> CheckResult:
    problems = []
    for label, expected in EXPECTED_WORKER_DENIALS.items():
        counts = denial_counts(_events(run_dir, label))
        if counts["worker"] != expected or counts["total"] != expected:
            problems.append(f"{label}: {counts} expected worker={expected}")
    return CheckResult("permission_denials_attributed", not problems, f"{problems or 'ok'}")


def check_no_delegation_in_config_a(run_dir: Path) -> CheckResult:
    problems = [
        f"{label}: {len(delegation_records(_events(run_dir, label)))} delegations"
        for label in CONFIG_A_LABELS
        if delegation_records(_events(run_dir, label))
    ]
    return CheckResult("config_a_has_no_delegation", not problems, f"{problems or 'ok'}")


def _phase_sum(events: list[dict[str, Any]], delegating: bool) -> int:
    totals = phase_totals(events, main_phase_boundary_tools(delegating))
    return sum(
        totals[name]["input_cache_tokens"] for name in (DECISION_PHASE, IMPLEMENTATION_PHASE)
    )


def check_phase_sum_matches_aggregate(run_dir: Path) -> CheckResult:
    problems = []
    for label in (*CONFIG_A_LABELS, *EXPECTED_DELEGATIONS):
        events = _events(run_dir, label)
        observed = _phase_sum(events, "config_b" in label)
        aggregate = _opus_input_cache(events)
        if observed != aggregate:
            problems.append(f"{label}: phases={observed} aggregate={aggregate}")
    return CheckResult("phase_totals_sum_to_aggregate", not problems, f"{problems or 'ok'}")


def check_decision_phase_nonempty(run_dir: Path) -> CheckResult:
    problems = []
    for label in CONFIG_A_LABELS:
        totals = phase_totals(_events(run_dir, label), WRITE_TOOLS)
        decision = totals[DECISION_PHASE]
        if decision["request_count"] == 0 or decision["input_cache_tokens"] == 0:
            problems.append(f"{label}: decision phase empty")
    return CheckResult("decision_phase_nonempty", not problems, f"{problems or 'ok'}")


def check_output_declared_unavailable(run_dir: Path) -> CheckResult:
    totals = phase_totals(_events(run_dir, CONFIG_A_LABELS[0]), WRITE_TOOLS)
    value = str(totals.get("output_tokens_per_phase", ""))
    return CheckResult(
        "output_tokens_per_phase_declared_unavailable", value.startswith("UNAVAILABLE"), value
    )


def run_all(run_dir: Path) -> list[CheckResult]:
    return [
        check_delegation_fields(run_dir),
        check_tool_stats_present(run_dir),
        check_denial_attribution(run_dir),
        check_no_delegation_in_config_a(run_dir),
        check_phase_sum_matches_aggregate(run_dir),
        check_decision_phase_nonempty(run_dir),
        check_output_declared_unavailable(run_dir),
    ]
