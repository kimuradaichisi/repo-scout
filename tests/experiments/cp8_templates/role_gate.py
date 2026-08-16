#!/usr/bin/env python3
"""Role-aware Write/Edit gate for CP8 Config B.

Step 0 established that a subagent's usable tools are the intersection of the
parent CLI's grant and the subagent's own declaration, so denying Write/Edit
on the command line to stop Main implementing also stopped the Worker
implementing -- which is the entire point of Config B. The grant therefore
moves back to the CLI, and the distinction moves here, where the caller's
identity is visible: PreToolUse fires with agent_id / agent_type set when the
call originates inside a subagent, and unset when it is Main's own.

This same settings.json (and this same hook) is installed in every CP8
snapshot, Config A's included, so the file cannot tell the two configs apart
by content. It reads the CP8_ACTIVE_CONFIG environment variable instead of a
file the run itself could rewrite -- the Sonnet Worker has Write/Edit, so a
file-based marker would have been something the experiment's own subject
could tamper with; an env var the harness sets before the `claude` process
even starts is not:

    Config A: Main writes directly            -> gate is a pass-through, logs only
    Config B: Write/Edit, no agent_id          -> DENY   (Main must not implement)
              Write/Edit, agent_type sonnet-worker -> ALLOW  (the Worker implements)
              Write/Edit, any other agent_type  -> DENY   (unknown delegate)

Denial is the default on anything unexpected -- an unparseable payload, a
missing tool name, CP8_ACTIVE_CONFIG unset or set to neither known value --
because a gate that fails open cannot be cited as the reason Main did not
write. Both the raw environment value and the value actually used (after
fail-closed normalization) are logged, so a propagation failure -- the
variable not reaching the hook at all -- is visible in the log rather than
silently indistinguishable from a deliberate config_b run.

Every decision is appended to .cp8/role_gate.log as one JSON object, including
the payload's key names, so that a run can be audited on what the hook
actually saw rather than on what it was assumed to receive.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

WORKER_AGENT_TYPE = "sonnet-worker"
GATED_TOOLS = frozenset({"Write", "Edit"})
LOG_RELATIVE = ".cp8/role_gate.log"
ACTIVE_CONFIG_ENV = "CP8_ACTIVE_CONFIG"
PASS_THROUGH_CONFIG = "config_a"
STRICT_CONFIG = "config_b"
KNOWN_CONFIGS = frozenset({PASS_THROUGH_CONFIG, STRICT_CONFIG})


def agent_identity(payload: dict[str, Any]) -> tuple[str, str]:
    """The calling agent's id and type, from either the flat or nested shape."""
    nested = payload.get("agent")
    nested = nested if isinstance(nested, dict) else {}
    agent_id = payload.get("agent_id") or nested.get("id") or nested.get("agent_id") or ""
    agent_type = payload.get("agent_type") or nested.get("type") or nested.get("agent_type") or ""
    return str(agent_id), str(agent_type)


def active_config() -> tuple[str, str]:
    """(raw env value, resolved config) -- unset or unrecognised fails closed to config_b."""
    raw = os.environ.get(ACTIVE_CONFIG_ENV, "")
    resolved = raw if raw in KNOWN_CONFIGS else STRICT_CONFIG
    return raw, resolved


def decide(tool_name: str, agent_id: str, agent_type: str, config: str) -> tuple[str, str]:
    """Return (decision, reason) for one Write/Edit attempt."""
    if tool_name not in GATED_TOOLS:
        return "SKIP", "not a gated tool"
    if config == PASS_THROUGH_CONFIG:
        return "ALLOW", "config_a: Main implements directly, role gate is a pass-through"
    if not agent_id:
        return (
            "DENY",
            "CP8 role gate: Main must not write. This change belongs to the Sonnet Worker — "
            "hand it over in an Implementation Pack instead of implementing it here. Do not "
            "retry, and do not reach for a shell to do the same thing.",
        )
    if agent_type == WORKER_AGENT_TYPE:
        return "ALLOW", f"delegated write by {WORKER_AGENT_TYPE}"
    return (
        "DENY",
        f"CP8 role gate: writes are permitted only to the {WORKER_AGENT_TYPE} subagent, "
        f"and this call came from {agent_type or 'an unnamed agent'}.",
    )


def log_decision(project_dir: Path, record: dict[str, Any]) -> None:
    log = project_dir / LOG_RELATIVE
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def emit_deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def read_payload() -> dict[str, Any] | None:
    try:
        parsed = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def project_directory(payload: dict[str, Any]) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or Path.cwd())


def build_record(
    payload: dict[str, Any],
    identity: tuple[str, str],
    decision: str,
    config: tuple[str, str],
) -> dict[str, Any]:
    """One audit line: who called, what for, and what the gate decided.

    Both the raw CP8_ACTIVE_CONFIG value and the resolved one are recorded, so
    a run where the env var never reached the hook shows up as a raw/resolved
    mismatch rather than looking identical to an intentional config_b run.
    payload_keys goes in too, so a run can be checked against the fields the
    hook actually received rather than the fields it expected to receive.
    """
    tool_input = payload.get("tool_input")
    target = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""
    return {
        "at": datetime.now().isoformat(timespec="seconds"),
        "decision": decision,
        "tool_name": str(payload.get("tool_name", "")),
        "agent_id": identity[0],
        "agent_type": identity[1],
        "active_config_raw": config[0],
        "active_config_resolved": config[1],
        "target": str(target),
        "payload_keys": sorted(payload),
    }


def main() -> int:
    payload = read_payload()
    if payload is None:
        emit_deny(
            "CP8 role gate: the hook payload could not be read, so the caller's role cannot "
            "be established. Refusing the write."
        )
        return 0

    config = active_config()
    identity = agent_identity(payload)
    decision, reason = decide(str(payload.get("tool_name", "")), *identity, config[1])
    log_decision(project_directory(payload), build_record(payload, identity, decision, config))

    if decision == "DENY":
        emit_deny(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
