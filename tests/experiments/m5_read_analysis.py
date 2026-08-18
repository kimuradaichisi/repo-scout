"""What actually re-entered model context, at Read-tool granularity.

Duplicate judgement is deterministic: path + line range + content sha256
(the minimum the instructions ask for). Range overlap is computed
additionally, at individual line granularity, independent of hash equality --
a broader signal for "the same source entered context again" per the
guardrail that call-count alone is not the answer.

Scope note: only the native Read tool is analyzed here. Bash-based reads
(cat/sed/head of a file) are not attributed to a path/range and are reported
separately as bash_read_calls (see m5_pack_calls.py) rather than folded into
this UNKNOWN-range population.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cp8_transcript import ToolCall, tool_calls, tool_results

_NUMBERED_LINE = re.compile(r"^(\d+)\t(.*)$")


@dataclass(frozen=True)
class ReadEvent:
    path: str
    start_line: int
    end_line: int
    content: str
    sha256: str


def _numbered_lines(content: str) -> list[tuple[int, str]]:
    matched = (_NUMBERED_LINE.match(line) for line in content.split("\n"))
    return [(int(m.group(1)), m.group(0)) for m in matched if m]


def _relative_path(root: Path, file_path: str) -> str:
    try:
        return str(Path(file_path).resolve().relative_to(root.resolve()))
    except ValueError:
        return file_path


def _to_read_event(call: ToolCall, content: str, root: Path) -> ReadEvent | None:
    lines = _numbered_lines(content)
    if not lines:
        return None
    file_path = call.payload.get("file_path")
    if not isinstance(file_path, str):
        return None
    return ReadEvent(
        path=_relative_path(root, file_path),
        start_line=lines[0][0],
        end_line=lines[-1][0],
        content=content,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def read_events(events: list[dict[str, Any]], root: Path) -> list[ReadEvent]:
    results = tool_results(events)
    reads: list[ReadEvent] = []
    for call in tool_calls(events):
        if call.name != "Read" or call.parent_tool_use_id is not None:
            continue
        event = _to_read_event(call, results.get(call.tool_use_id, ""), root)
        if event is not None:
            reads.append(event)
    return reads


def repeat_metrics(reads: list[ReadEvent]) -> dict[str, int]:
    seen_exact: set[tuple[str, int, int, str]] = set()
    seen_lines: dict[str, set[int]] = {}
    repeated_calls = 0
    repeated_bytes = 0
    overlap_bytes = 0

    for event in reads:
        key = (event.path, event.start_line, event.end_line, event.sha256)
        if key in seen_exact:
            repeated_calls += 1
            repeated_bytes += len(event.content.encode("utf-8"))
        seen_exact.add(key)
        overlap_bytes += _overlap_bytes(event, seen_lines.setdefault(event.path, set()))

    return {
        "repeated_read_calls": repeated_calls,
        "repeated_source_bytes": repeated_bytes,
        "range_overlap_bytes": overlap_bytes,
    }


def _overlap_bytes(event: ReadEvent, seen_lines: set[int]) -> int:
    lines = _numbered_lines(event.content)
    overlap = sum(len(text.encode("utf-8")) + 1 for number, text in lines if number in seen_lines)
    seen_lines.update(number for number, _ in lines)
    return overlap


def unique_read_paths(reads: list[ReadEvent]) -> int:
    return len({event.path for event in reads})


def fictional_read_paths(reads: list[ReadEvent], tracked_paths: list[str]) -> list[str]:
    tracked = set(tracked_paths)
    return sorted({event.path for event in reads if event.path not in tracked})
