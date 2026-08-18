"""How much of the Pack's context the Worker had to go and re-acquire.

Delegation only pays if the Implementation Pack actually carries the context
Main gathered. A Worker that re-greps the repository from scratch has been
handed a task, not a handoff, and the tokens Main saved reappear one level
down. These metrics measure that directly, by separating the Worker's reads
and searches into the ones the Pack pointed at and the ones it did not.

A call counts as inside the Pack when any path it names matches a TARGET FILES
or RELEVANT EVIDENCE entry. A call naming no path at all -- `ls src`, a bare
grep -- counts as outside: the Pack did not send the Worker there.
"""

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_metrics import (
    BASH_READ_COMMANDS,
    BASH_SEARCH_COMMANDS,
    BASH_SEPARATORS,
    READ_LIKE_TOOLS,
    SEARCH_LIKE_TOOLS,
)
from cp8_transcript import ToolCall, model_usage, tool_calls, tool_results

WRITE_LIKE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})
PATH_KEYS = ("file_path", "path", "notebook_path")


@dataclass(frozen=True)
class WorkerMetrics:
    worker_read_count: int = 0
    worker_search_count: int = 0
    worker_outside_pack_read_count: int = 0
    worker_fallback_exploration_volume: int = 0
    worker_write_count: int = 0
    worker_tool_calls: dict[str, int] = field(default_factory=dict)
    nested_calls_observed: bool = False


@dataclass(frozen=True)
class DelegationObservation:
    tool_name: str
    tool_use_id: str
    subagent_type: str | None
    has_model_override: bool
    result_chars: int


def call_paths(call: ToolCall) -> list[str]:
    """Every path the call names, from its own arguments and any bash words."""
    paths = [str(call.payload[key]) for key in PATH_KEYS if isinstance(call.payload.get(key), str)]
    command = call.payload.get("command")
    if isinstance(command, str):
        paths.extend(_bash_words(command))
    return [path for path in paths if path]


def _bash_words(command: str) -> list[str]:
    words: list[str] = []
    for segment in BASH_SEPARATORS.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        words.extend(token for token in tokens[1:] if not token.startswith("-"))
    return words


def _bash_kinds(command: str) -> set[str]:
    kinds: set[str] = set()
    for segment in BASH_SEPARATORS.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        words = [token for token in tokens if not token.startswith("-")]
        if not words:
            continue
        binary = Path(words[0]).name
        if binary in BASH_READ_COMMANDS:
            kinds.add("read")
        elif binary in BASH_SEARCH_COMMANDS:
            kinds.add("search")
    return kinds


def call_kinds(call: ToolCall) -> set[str]:
    """Whether a call reads, searches, writes -- a Bash call can do several."""
    kinds: set[str] = set()
    if call.name in READ_LIKE_TOOLS:
        kinds.add("read")
    if call.name in SEARCH_LIKE_TOOLS:
        kinds.add("search")
    if call.name in WRITE_LIKE_TOOLS:
        kinds.add("write")
    command = call.payload.get("command")
    if call.name == "Bash" and isinstance(command, str):
        kinds |= _bash_kinds(command)
    return kinds


def is_inside_pack(call: ToolCall, pack_paths: frozenset[str]) -> bool:
    if not pack_paths:
        return False
    for named in call_paths(call):
        stem = named.lstrip("./")
        if any(stem.endswith(pack) or pack.endswith(stem) for pack in pack_paths):
            return True
    return False


@dataclass
class _Tally:
    counts: dict[str, int] = field(default_factory=lambda: {"read": 0, "search": 0, "write": 0})
    outside_reads: int = 0
    volume: int = 0
    by_name: dict[str, int] = field(default_factory=dict)


def _tally(calls: list[ToolCall], results: dict[str, str], pack_paths: frozenset[str]) -> _Tally:
    tally = _Tally()
    for call in calls:
        tally.by_name[call.name] = tally.by_name.get(call.name, 0) + 1
        kinds = call_kinds(call)
        for kind in tally.counts:
            tally.counts[kind] += 1 if kind in kinds else 0
        if not kinds & {"read", "search"} or is_inside_pack(call, pack_paths):
            continue
        tally.outside_reads += 1 if "read" in kinds else 0
        tally.volume += len(results.get(call.tool_use_id, ""))
    return tally


def worker_metrics(events: list[dict[str, Any]], pack_paths: frozenset[str]) -> WorkerMetrics:
    """Aggregate the nested (subagent) calls found in a parent transcript."""
    nested = [call for call in tool_calls(events) if call.is_nested]
    if not nested:
        return WorkerMetrics()

    tally = _tally(nested, tool_results(events), pack_paths)
    return WorkerMetrics(
        worker_read_count=tally.counts["read"],
        worker_search_count=tally.counts["search"],
        worker_outside_pack_read_count=tally.outside_reads,
        worker_fallback_exploration_volume=tally.volume,
        worker_write_count=tally.counts["write"],
        worker_tool_calls=tally.by_name,
        nested_calls_observed=True,
    )


DENIAL_PHRASES = (
    "was blocked",
    "requires approval",
    "permission",
    "not allowed",
    "may only",
)


def worker_permission_denial_count(events: list[dict[str, Any]]) -> int:
    """Nested tool calls whose own result reads as a refusal.

    The CLI's own permission_denials list (claude_metrics.py) is aggregated on
    the run's top-level result with no parent_tool_use_id, so it cannot say
    whether Main or the Worker hit the denial. A denied *nested* call, though,
    still gets a tool_result on that call -- carrying the refusal text, which
    is how the Worker learns about it at all -- so scanning nested results for
    that text attributes the denial correctly. Heuristic (text-pattern based),
    not a structured field Claude Code exposes.
    """
    results = tool_results(events)
    nested = [call for call in tool_calls(events) if call.is_nested]
    count = 0
    for call in nested:
        text = results.get(call.tool_use_id, "").lower()
        if any(phrase in text for phrase in DENIAL_PHRASES):
            count += 1
    return count


def delegation_observations(events: list[dict[str, Any]]) -> list[DelegationObservation]:
    """Every Agent / Task call Main made, and whether it overrode the model."""
    results = tool_results(events)
    observations = []
    for call in tool_calls(events):
        if not call.is_delegation:
            continue
        subagent = call.payload.get("subagent_type")
        observations.append(
            DelegationObservation(
                tool_name=call.name,
                tool_use_id=call.tool_use_id,
                subagent_type=str(subagent) if isinstance(subagent, str) else None,
                has_model_override="model" in call.payload,
                result_chars=len(results.get(call.tool_use_id, "")),
            )
        )
    return observations


def _tokens(entry: Any, *names: str) -> int:
    if not isinstance(entry, dict):
        return 0
    return sum(int(entry.get(name, 0) or 0) for name in names)


def model_separation(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Split the run's reported modelUsage into its Opus and Sonnet halves."""
    usage = model_usage(events)
    opus = {name: entry for name, entry in usage.items() if "opus" in name.lower()}
    sonnet = {name: entry for name, entry in usage.items() if "sonnet" in name.lower()}
    sonnet_out = sum(_tokens(entry, "outputTokens", "output_tokens") for entry in sonnet.values())
    opus_out = sum(_tokens(entry, "outputTokens", "output_tokens") for entry in opus.values())
    return {
        "models_observed": sorted(usage),
        "opus_models": sorted(opus),
        "sonnet_models": sorted(sonnet),
        "opus_output_tokens": opus_out,
        "sonnet_output_tokens": sonnet_out,
        "separated": bool(opus) and bool(sonnet),
        "sonnet_tokens_positive": sonnet_out > 0,
        "raw_model_usage": usage,
    }
