"""Read a saved stream-json transcript back out of a CP8 run.

claude_metrics.py already parses transcripts, but it parses them while a run
is happening and it is shared with every CP0-CP7 experiment. CP8 needs two
things it does not collect -- the tool calls a subagent made inside its own
context, and the volume of text tool results fed back -- so CP8 re-reads the
saved .jsonl instead of changing the collector every earlier result was
produced by.

Nested events are identified by `parent_tool_use_id`: an event carrying one
was produced inside the subagent invoked by that tool call, not by Main.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Claude Code renamed the delegation tool Task -> Agent. Recognise both, so a
# transcript is read correctly whichever name the running version emitted.
DELEGATION_TOOL_NAMES = frozenset({"Agent", "Task"})


@dataclass(frozen=True)
class ToolCall:
    name: str
    tool_use_id: str
    parent_tool_use_id: str | None
    payload: dict[str, Any]

    @property
    def is_delegation(self) -> bool:
        return self.name in DELEGATION_TOOL_NAMES

    @property
    def is_nested(self) -> bool:
        """True when this call was made inside a subagent rather than by Main."""
        return self.parent_tool_use_id is not None


def load_events(transcript: Path) -> list[dict[str, Any]]:
    if not transcript.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    content = event.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def tool_calls(events: list[dict[str, Any]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        parent = event.get("parent_tool_use_id")
        for block in _content_blocks(event):
            if block.get("type") != "tool_use":
                continue
            payload = block.get("input")
            calls.append(
                ToolCall(
                    name=str(block.get("name", "unknown")),
                    tool_use_id=str(block.get("id", "")),
                    parent_tool_use_id=str(parent) if parent else None,
                    payload=payload if isinstance(payload, dict) else {},
                )
            )
    return calls


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        str(item.get("text", ""))
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "".join(parts)


def tool_results(events: list[dict[str, Any]]) -> dict[str, str]:
    """tool_use_id -> the text handed back to the model for that call."""
    results: dict[str, str] = {}
    for event in events:
        if event.get("type") != "user":
            continue
        for block in _content_blocks(event):
            if block.get("type") != "tool_result":
                continue
            results[str(block.get("tool_use_id", ""))] = _result_text(block)
    return results


def result_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("type") == "result":
            return event
    return {}


def model_usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    usage = result_event(events).get("modelUsage", {})
    return usage if isinstance(usage, dict) else {}


def permission_denials(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    denials = result_event(events).get("permission_denials", [])
    if not isinstance(denials, list):
        return []
    return [item for item in denials if isinstance(item, dict)]


def final_text(events: list[dict[str, Any]]) -> str:
    return str(result_event(events).get("result", "") or "")
