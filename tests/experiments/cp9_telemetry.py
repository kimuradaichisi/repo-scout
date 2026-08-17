"""Structured run telemetry for CP9, read straight from the saved transcript.

CP8 inferred several of these facts and said so: the Worker's model came from
which entries appeared in modelUsage, its tool counts came from counting
nested calls, and permission denials were attributed by matching refusal
phrases in result text. The transcript turns out to carry all three as
structured fields already -- the Agent tool_result reports `resolvedModel`,
`agentType`, `toolStats` and `totalDurationMs`, and denials arrive as
`system`/`permission_denied` events carrying `agent_id` -- so CP9 reads them
instead of inferring them. CP8's modules are left exactly as they were.

The one thing that genuinely cannot be recovered is per-phase output tokens.
Assistant rows are streamed, and each row's `usage.output_tokens` is a
snapshot taken mid-stream, not the final count: summing the last row per
request reproduces input / cache_read / cache_creation exactly against the
run's aggregate modelUsage, and reproduces output as 43 where the true figure
is 12,113. So phase totals here report input and cache only, and say so;
output stays at run level where the `result` event reports it correctly. No
proportional split is invented to fill the gap.
"""

from dataclasses import dataclass
from typing import Any

WRITE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})
DELEGATION_TOOLS = frozenset({"Agent", "Task"})

DECISION_PHASE = "decision"
IMPLEMENTATION_PHASE = "implementation"


@dataclass(frozen=True)
class PhaseTotals:
    request_count: int
    input_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    tool_calls: int
    elapsed_seconds: float | None

    @property
    def input_cache_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_creation_tokens


def _blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    content = event.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def tool_use_names(event: dict[str, Any]) -> list[str]:
    return [str(b.get("name", "")) for b in _blocks(event) if b.get("type") == "tool_use"]


def _request_key(event: dict[str, Any]) -> str:
    return str(event.get("request_id") or event.get("message", {}).get("id") or id(event))


def _usage(event: dict[str, Any]) -> dict[str, int]:
    usage = event.get("message", {}).get("usage", {})
    usage = usage if isinstance(usage, dict) else {}
    return {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
        "cache_creation_tokens": int(usage.get("cache_creation_input_tokens", 0) or 0),
    }


def main_assistant_requests(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per Main request, in order, carrying its final usage row.

    Streaming emits a request several times; the last row holds the settled
    input/cache figures, while dict insertion order keeps the first sighting's
    position so phase assignment stays chronological.
    """
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "assistant" or event.get("parent_tool_use_id"):
            continue
        latest[_request_key(event)] = event
    return list(latest.values())


def phase_of_requests(
    events: list[dict[str, Any]], boundary_tools: frozenset[str]
) -> dict[str, str]:
    """request key -> decision / implementation, split at the first boundary call."""
    phases: dict[str, str] = {}
    crossed = False
    for event in events:
        if event.get("type") != "assistant" or event.get("parent_tool_use_id"):
            continue
        key = _request_key(event)
        if key not in phases:
            phases[key] = IMPLEMENTATION_PHASE if crossed else DECISION_PHASE
        if not crossed and any(name in boundary_tools for name in tool_use_names(event)):
            crossed = True
    return phases


def _elapsed(rows: list[dict[str, Any]]) -> float | None:
    stamps = sorted(str(row.get("timestamp", "")) for row in rows if row.get("timestamp"))
    if len(stamps) < 2:
        return None
    from datetime import datetime

    try:
        start = datetime.fromisoformat(stamps[0].replace("Z", "+00:00"))
        end = datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((end - start).total_seconds(), 3)


def phase_totals(events: list[dict[str, Any]], boundary_tools: frozenset[str]) -> dict[str, Any]:
    """Decision- and implementation-phase input/cache totals for Main."""
    phases = phase_of_requests(events, boundary_tools)
    buckets: dict[str, list[dict[str, Any]]] = {DECISION_PHASE: [], IMPLEMENTATION_PHASE: []}
    for row in main_assistant_requests(events):
        buckets[phases.get(_request_key(row), DECISION_PHASE)].append(row)
    return {name: _bucket_totals(rows) for name, rows in buckets.items()} | {
        "output_tokens_per_phase": "UNAVAILABLE (streamed usage is not final per row)"
    }


def _bucket_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = PhaseTotals(
        request_count=len(rows),
        input_tokens=sum(_usage(row)["input_tokens"] for row in rows),
        cache_read_tokens=sum(_usage(row)["cache_read_tokens"] for row in rows),
        cache_creation_tokens=sum(_usage(row)["cache_creation_tokens"] for row in rows),
        tool_calls=sum(len(tool_use_names(row)) for row in rows),
        elapsed_seconds=_elapsed(rows),
    )
    return {
        "request_count": totals.request_count,
        "input_tokens": totals.input_tokens,
        "cache_read_tokens": totals.cache_read_tokens,
        "cache_creation_tokens": totals.cache_creation_tokens,
        "input_cache_tokens": totals.input_cache_tokens,
        "tool_calls": totals.tool_calls,
        "elapsed_seconds": totals.elapsed_seconds,
    }


def delegation_records(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every Agent hand-off, as the transcript's own structured report of it."""
    records = []
    for event in events:
        payload = event.get("tool_use_result")
        if not isinstance(payload, dict) or "agentType" not in payload:
            continue
        stats = payload.get("toolStats") if isinstance(payload.get("toolStats"), dict) else {}
        records.append(
            {
                "agent_type": payload.get("agentType"),
                "agent_id": payload.get("agentId"),
                "resolved_model": payload.get("resolvedModel"),
                "status": payload.get("status"),
                "duration_ms": payload.get("totalDurationMs"),
                "tool_use_count": payload.get("totalToolUseCount"),
                "tool_stats": stats,
                "contract_chars": len(str(payload.get("prompt", ""))),
                "result_pack_chars": len(str(payload.get("content", ""))),
            }
        )
    return records


def permission_denied_records(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Denials as structured events, so Main's and the Worker's are separable."""
    return [
        {
            "tool_name": event.get("tool_name"),
            "agent_id": event.get("agent_id"),
            "decision_reason": event.get("decision_reason"),
            "attributed_to": "worker" if event.get("agent_id") else "main",
        }
        for event in events
        if event.get("type") == "system" and event.get("subtype") == "permission_denied"
    ]


def denial_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    records = permission_denied_records(events)
    return {
        "total": len(records),
        "main": sum(1 for r in records if r["attributed_to"] == "main"),
        "worker": sum(1 for r in records if r["attributed_to"] == "worker"),
    }


def observed_models(events: list[dict[str, Any]]) -> list[str]:
    names = {
        str(e.get("message", {}).get("model"))
        for e in events
        if e.get("type") == "assistant" and e.get("message", {}).get("model")
    }
    return sorted(names)


def main_phase_boundary_tools(is_delegating: bool) -> frozenset[str]:
    """Where Main stops deciding: its first hand-off, or its first own edit."""
    return DELEGATION_TOOLS if is_delegating else WRITE_TOOLS


def main_write_calls(events: list[dict[str, Any]]) -> int:
    """Write/Edit calls Main issued itself, counted from its own (non-nested) turns.

    Distinct from the role gate's denial count: the gate records attempts it
    refused, this records calls Main made. Under Config B both should be zero
    for different reasons, and a disagreement between them is worth seeing.
    """
    return sum(
        1
        for row in main_assistant_requests(events)
        for name in tool_use_names(row)
        if name in WRITE_TOOLS
    )
