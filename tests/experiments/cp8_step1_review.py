"""Config B role-adherence and review-integrity metrics for CP8 Step 1.

Everything here reads a recorded artifact -- the role gate's own log, the
pre_worker_diff_empty gate's own log, the Worker's actual Result Pack text,
the harness's own independently-run gates -- rather than Main's account of
what happened. review_gate_match in particular is deliberately computed
against the harness's authoritative gate run (cp8_step1_gates.py), not
against what Main's final report claims to have found, so a Main that skips
its own review cannot report a match that never happened.
"""

import re
from dataclasses import dataclass
from typing import Any

from cp8_packs import RESULT_PACK_SECTIONS, extract_target_files, split_sections
from cp8_step0a_checks import parse_role_log
from cp8_tasks import scope_violations
from cp8_transcript import tool_calls, tool_results
from cp8_worker_metrics import delegation_observations

GATE_RED_FLAGS = ("fail", "error", "not run", "did not run", "skipped", "n/a")
_PATH = re.compile(r"[\w./-]+\.(?:py|md|toml|lock|yaml|yml|sh)\b")


@dataclass(frozen=True)
class DelegationRound:
    pack_text: str
    result_pack_text: str


def delegation_rounds(events: list[dict[str, Any]]) -> list[DelegationRound]:
    """Every Agent call Main made, paired with the Pack it sent and got back.

    The Pack text is the call's own `prompt` input -- what Main actually told
    the Worker -- not a document reconstructed after the fact.
    """
    results = tool_results(events)
    return [
        DelegationRound(
            pack_text=str(call.payload.get("prompt", "")),
            result_pack_text=results.get(call.tool_use_id, ""),
        )
        for call in tool_calls(events)
        if call.is_delegation
    ]


def main_direct_write_count(main_role_log_text: str) -> int:
    """Write/Edit attempts the role gate attributed to Main (no agent_id)."""
    records = parse_role_log(main_role_log_text)
    return sum(1 for r in records if r.get("decision") == "DENY" and not r.get("agent_id"))


def active_config_propagation(role_log_text: str, expected_config: str) -> dict[str, Any]:
    """Did CP8_ACTIVE_CONFIG actually reach the hook as the harness set it?

    Compares every logged active_config_raw against what this run intended
    (expected_config), so a propagation failure — the env var never reaching
    the hook subprocess — shows up as a raw/expected mismatch rather than
    passing silently as a same-looking config_b run.
    """
    records = parse_role_log(role_log_text)
    raw_values = sorted({r.get("active_config_raw", "") for r in records})
    return {
        "gated_call_count": len(records),
        "raw_values_observed": raw_values,
        "matches_expected": bool(records) and raw_values == [expected_config],
    }


def pre_worker_diff_empty(pre_worker_log_text: str) -> bool | None:
    """Whether every delegation attempt found a clean tree.

    None means Main never attempted delegation at all -- a different
    condition from "attempted and always found it clean", and one the caller
    should not silently treat as passing.
    """
    if not pre_worker_log_text.strip():
        return None
    return "DENY" not in pre_worker_log_text


def rework_cycles(events: list[dict[str, Any]]) -> int:
    """Delegation calls beyond the first — capped at 1 by the prompt, not code."""
    return max(0, len(delegation_observations(events)) - 1)


def worker_claims_gates_green(result_pack_text: str) -> bool:
    """Absence-of-red-flags reading of the Worker's own QUALITY GATE RESULTS."""
    sections = split_sections(result_pack_text, RESULT_PACK_SECTIONS)
    body = sections.get("QUALITY GATE RESULTS", "").lower()
    if not body:
        return False
    return not any(flag in body for flag in GATE_RED_FLAGS)


def review_gate_match(result_pack_text: str, authoritative_gate_pass: bool) -> bool:
    """Does the Worker's claim match the harness's own independent gate run?"""
    return worker_claims_gates_green(result_pack_text) == authoritative_gate_pass


def unknown_blocked_count(result_pack_text: str) -> int:
    """Non-'(none)' bullet lines under the Worker's UNKNOWN / BLOCKED section."""
    sections = split_sections(result_pack_text, RESULT_PACK_SECTIONS)
    body = sections.get("UNKNOWN / BLOCKED", "").strip()
    if not body or body.lower().startswith("(none"):
        return 0
    return sum(1 for line in body.splitlines() if line.strip().startswith(("-", "*")))


def worker_scope_violation_count(pack_texts: list[str], changed_paths: list[str]) -> int:
    """Changed paths none of the sent Packs declared as TARGET FILES.

    Takes every Pack sent in the run (plural, for the rework case) and unions
    their TARGET FILES, since a file legitimately touched only in a
    corrective second Pack must not be flagged as out of scope.
    """
    target_files: frozenset[str] = frozenset()
    for text in pack_texts:
        target_files |= extract_target_files(text)
    if not target_files:
        return len(changed_paths)
    violations = 0
    for path in changed_paths:
        stem = path.lstrip("./")
        if not any(stem.endswith(t) or t.endswith(stem) for t in target_files):
            violations += 1
    return violations


def diff_scope_violation_count(changed_paths: list[str], task: dict[str, Any]) -> int:
    """Changed paths the task itself forbids — applies to both configs."""
    return len(scope_violations(changed_paths, task))
