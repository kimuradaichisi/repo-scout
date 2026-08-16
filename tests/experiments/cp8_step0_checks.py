"""Evaluate the twelve CP8 Step 0 infrastructure checks from run artifacts.

Every check reads a recorded artifact -- a transcript, a hook log, a file
hash -- rather than the model's own account of what happened. Step 0 exists to
find out whether the measurement apparatus works, and a probe that trusts the
subject to report on the apparatus has not checked it.
"""

from dataclasses import dataclass, field
from typing import Any

from cp8_permissions import BASH_ALLOWLIST
from cp8_transcript import permission_denials
from cp8_worker_metrics import delegation_observations, model_separation, worker_metrics

ALLOWED_PREFIXES = tuple(item[len("Bash(") : -len(":*)")] for item in BASH_ALLOWLIST)
WRITE_ESCAPES = ("sed", "tee", "cat >", "python")


@dataclass(frozen=True)
class Check:
    number: int
    title: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Step0Artifacts:
    probe_a: list[dict[str, Any]] = field(default_factory=list)
    probe_b: list[dict[str, Any]] = field(default_factory=list)
    probe_c: list[dict[str, Any]] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    readme_sha_before: str = ""
    readme_sha_after: str = ""
    gate_log_b: str = ""
    gate_log_c: str = ""
    leak_count: int = 0
    scout_evidence_exists: bool = False


def _denied_commands(events: list[dict[str, Any]]) -> list[str]:
    commands = []
    for denial in permission_denials(events):
        payload = denial.get("tool_input", {})
        if isinstance(payload, dict) and isinstance(payload.get("command"), str):
            commands.append(payload["command"])
    return commands


def check_agent_invocable(artifacts: Step0Artifacts) -> Check:
    calls = delegation_observations(artifacts.probe_b)
    answered = [call for call in calls if call.result_chars > 0]
    names = sorted({call.tool_name for call in calls})
    return Check(
        1,
        "headless claude -p can invoke a custom Sonnet subagent",
        bool(answered),
        f"delegation calls={len(calls)} answered={len(answered)} tool_names={names or '(none)'}",
    )


def check_subagent_model_env(artifacts: Step0Artifacts) -> Check:
    value = artifacts.environment.get("subagent_model_env")
    return Check(
        2,
        "CLAUDE_CODE_SUBAGENT_MODEL is unset",
        value is None,
        f"CLAUDE_CODE_SUBAGENT_MODEL={value if value is not None else '<unset>'}",
    )


def check_no_model_override(artifacts: Step0Artifacts) -> Check:
    calls = delegation_observations(artifacts.probe_b)
    overrides = [call for call in calls if call.has_model_override]
    subagents = sorted({call.subagent_type or "?" for call in calls})
    return Check(
        3,
        "the Agent invocation carries no model override",
        bool(calls) and not overrides,
        f"calls={len(calls)} with_model_override={len(overrides)} subagent_type={subagents}",
    )


def check_model_separation(artifacts: Step0Artifacts) -> Check:
    separation = model_separation(artifacts.probe_b)
    return Check(
        4,
        "measured modelUsage separates Opus from Sonnet",
        separation["separated"],
        f"models_observed={separation['models_observed']}",
    )


def check_sonnet_tokens(artifacts: Step0Artifacts) -> Check:
    separation = model_separation(artifacts.probe_b)
    return Check(
        5,
        "Sonnet-side token usage is positive",
        separation["sonnet_tokens_positive"],
        f"sonnet_output_tokens={separation['sonnet_output_tokens']} "
        f"opus_output_tokens={separation['opus_output_tokens']}",
    )


def check_worker_tools_observable(artifacts: Step0Artifacts) -> Check:
    metrics = worker_metrics(artifacts.probe_b, frozenset())
    return Check(
        6,
        "the Worker's own tool calls are observable from the parent transcript",
        metrics.nested_calls_observed,
        f"nested_tool_calls={metrics.worker_tool_calls or '(none)'} "
        f"read={metrics.worker_read_count} search={metrics.worker_search_count} "
        f"write={metrics.worker_write_count}",
    )


def check_hook_denies_dirty(artifacts: Step0Artifacts) -> Check:
    denied = "DENY" in artifacts.gate_log_c
    ran_worker = worker_metrics(artifacts.probe_c, frozenset()).nested_calls_observed
    return Check(
        7,
        "the PreToolUse hook denies delegation on a dirty tree",
        denied and not ran_worker,
        f"gate_log={artifacts.gate_log_c.strip()[:120] or '(empty)'} worker_ran={ran_worker}",
    )


def check_hook_allows_clean(artifacts: Step0Artifacts) -> Check:
    allowed = "ALLOW" in artifacts.gate_log_b
    answered = any(call.result_chars > 0 for call in delegation_observations(artifacts.probe_b))
    return Check(
        8,
        "the PreToolUse hook allows delegation on a clean tree",
        allowed and answered,
        f"gate_log={artifacts.gate_log_b.strip()[:120] or '(empty)'} answered={answered}",
    )


def check_bash_allowlist(artifacts: Step0Artifacts) -> Check:
    denied = _denied_commands(artifacts.probe_a)
    wrongly = [cmd for cmd in denied if cmd.strip().startswith(ALLOWED_PREFIXES)]
    return Check(
        9,
        "the Bash allowlist covers Main's read/check work",
        not wrongly,
        f"denied={len(denied)} allowlisted_but_denied={wrongly or '(none)'}",
    )


def check_write_escapes_blocked(artifacts: Step0Artifacts) -> Check:
    denied = _denied_commands(artifacts.probe_a)
    attempted = [cmd for cmd in denied if cmd.strip().startswith(WRITE_ESCAPES)]
    unchanged = artifacts.readme_sha_before == artifacts.readme_sha_after
    return Check(
        10,
        "unrestricted write paths are unavailable to Main",
        unchanged and bool(attempted),
        f"readme_unchanged={unchanged} write_escapes_denied={len(attempted)} "
        f"(commands={[cmd[:40] for cmd in attempted] or '(none attempted)'})",
    )


def check_scout(artifacts: Step0Artifacts) -> Check:
    return Check(
        11,
        "./scout runs RepoScout against the snapshot without leaking repo_root",
        artifacts.scout_evidence_exists and artifacts.leak_count == 0,
        f"evidence_written={artifacts.scout_evidence_exists} leaks={artifacts.leak_count}",
    )


def check_hashes(artifacts: Step0Artifacts) -> Check:
    hashes: dict[str, str] = artifacts.environment.get("fixed_condition_hashes", {})
    missing = [name for name, value in hashes.items() if value in {"ABSENT", "UNKNOWN"}]
    return Check(
        12,
        "every fixed condition is hashed into the artifact",
        bool(hashes) and not missing,
        f"recorded={sorted(hashes)} missing={missing or '(none)'}",
    )


CHECKS = (
    check_agent_invocable,
    check_subagent_model_env,
    check_no_model_override,
    check_model_separation,
    check_sonnet_tokens,
    check_worker_tools_observable,
    check_hook_denies_dirty,
    check_hook_allows_clean,
    check_bash_allowlist,
    check_write_escapes_blocked,
    check_scout,
    check_hashes,
)


def run_checks(artifacts: Step0Artifacts) -> list[Check]:
    return [check(artifacts) for check in CHECKS]
