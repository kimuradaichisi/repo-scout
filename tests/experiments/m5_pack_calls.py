"""Bash calls into the reposcout CLI, and Reads that followed a pack call.

Detection is by command *tokens*, not a substring search: the snapshot
itself lives at a path like /tmp/reposcout-m5-.../target, so a plain `find`
or `grep` naming that path contains the word "reposcout" without invoking
the CLI at all. Matching substrings counted those as calls; this doesn't.
"""

import json
import re
import shlex
from pathlib import Path
from typing import Any

from cp8_transcript import ToolCall, tool_calls, tool_results

BASH_SEPARATORS = re.compile(r"&&|\|\||[;|\n]")


def _bash_calls(events: list[dict[str, Any]]) -> list[ToolCall]:
    return [
        call
        for call in tool_calls(events)
        if call.name == "Bash" and call.parent_tool_use_id is None
    ]


def _invokes_reposcout(command: str, subcommand: str | None = None) -> bool:
    for segment in BASH_SEPARATORS.split(command):
        try:
            words = [t for t in shlex.split(segment) if not t.startswith("-")]
        except ValueError:
            continue
        if not words or Path(words[0]).name != "reposcout":
            continue
        if subcommand is None or (len(words) > 1 and words[1] == subcommand):
            return True
    return False


def reposcout_call_count(events: list[dict[str, Any]]) -> int:
    return sum(
        _invokes_reposcout(str(call.payload.get("command", ""))) for call in _bash_calls(events)
    )


def pack_call_count(events: list[dict[str, Any]]) -> int:
    return sum(
        _invokes_reposcout(str(call.payload.get("command", "")), "pack")
        for call in _bash_calls(events)
    )


def pack_call_metrics(events: list[dict[str, Any]]) -> dict[str, int]:
    """Sum PackMetrics across every successful `reposcout pack` Bash call."""
    results = tool_results(events)
    packed_bytes = 0
    eliminated_bytes = 0
    for call in _bash_calls(events):
        command = str(call.payload.get("command", ""))
        if not _invokes_reposcout(command, "pack"):
            continue
        payload = _parse_pack_output(results.get(call.tool_use_id, ""))
        if payload is None:
            continue
        packed_bytes += int(payload.get("packed_source_bytes", 0))
        eliminated_bytes += int(payload.get("duplicate_or_overlap_bytes_eliminated", 0))
    return {
        "packed_source_bytes": packed_bytes,
        "duplicate_or_overlap_bytes_eliminated": eliminated_bytes,
    }


def _parse_pack_output(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    return metrics if isinstance(metrics, dict) else None


def final_direct_reads_after_pack(events: list[dict[str, Any]]) -> int:
    """Read tool calls whose chronological position follows the first pack call."""
    ordered_names: list[str] = []
    for call in tool_calls(events):
        if call.parent_tool_use_id is not None:
            continue
        if call.name == "Bash":
            command = str(call.payload.get("command", ""))
            if _invokes_reposcout(command, "pack"):
                ordered_names.append("pack")
        elif call.name == "Read":
            ordered_names.append("read")

    if "pack" not in ordered_names:
        return 0
    first_pack = ordered_names.index("pack")
    return ordered_names[first_pack:].count("read")
