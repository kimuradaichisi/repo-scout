"""Headless Claude Code invocation with token / tool-call instrumentation."""

import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

READ_LIKE_TOOLS = {"Read", "NotebookRead"}
SEARCH_LIKE_TOOLS = {"Grep", "Glob"}

# Claude reads and greps through Bash just as often as through the dedicated
# tools, so both have to be counted or the call metrics are meaningless.
BASH_READ_COMMANDS = {"cat", "head", "tail", "less", "more", "bat", "sed", "awk", "wc"}
BASH_SEARCH_COMMANDS = {"rg", "grep", "egrep", "fgrep", "ag", "ack", "find", "ls", "git"}
BASH_SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
FILE_LIKE = re.compile(r"^[\w./*@{}-]+\.\w+$")


@dataclass
class ClaudeRun:
    label: str
    exit_code: int
    wall_seconds: float

    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    num_turns: int = 0
    duration_ms: int = 0
    duration_api_ms: int = 0

    tool_calls: dict[str, int] = field(default_factory=dict)
    bash_read_calls: int = 0
    bash_search_calls: int = 0
    files_touched: list[str] = field(default_factory=list)
    permission_denials: list[str] = field(default_factory=list)
    model_usage: dict[str, Any] = field(default_factory=dict)

    final_text: str = ""
    transcript_path: str = ""
    error: str = ""

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.output_tokens

    @property
    def grep_calls(self) -> int:
        native = sum(self.tool_calls.get(name, 0) for name in SEARCH_LIKE_TOOLS)
        return native + self.bash_search_calls

    @property
    def read_calls(self) -> int:
        native = sum(self.tool_calls.get(name, 0) for name in READ_LIKE_TOOLS)
        return native + self.bash_read_calls

    @property
    def bash_calls(self) -> int:
        return self.tool_calls.get("Bash", 0)

    @property
    def file_count(self) -> int:
        return len(self.files_touched)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "exit_code": self.exit_code,
            "wall_seconds": round(self.wall_seconds, 3),
            "input_tokens": self.input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "total_input_tokens": self.total_input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "num_turns": self.num_turns,
            "duration_ms": self.duration_ms,
            "duration_api_ms": self.duration_api_ms,
            "tool_calls": self.tool_calls,
            "bash_read_calls": self.bash_read_calls,
            "bash_search_calls": self.bash_search_calls,
            "grep_calls": self.grep_calls,
            "read_calls": self.read_calls,
            "bash_calls": self.bash_calls,
            "file_count": self.file_count,
            "files_touched": self.files_touched,
            "permission_denials": self.permission_denials,
            "model_usage": self.model_usage,
            "transcript_path": self.transcript_path,
            "error": self.error,
        }


def run_claude(
    prompt: str,
    *,
    label: str,
    root: Path,
    transcript_path: Path,
    model: str = "claude-opus-5",
    allowed_tools: str = "Read,Grep,Glob",
    disallowed_tools: str = "Write,Edit,Task,WebFetch,WebSearch,Bash",
    timeout_seconds: int = 900,
) -> ClaudeRun:
    """Run one headless Claude Code turn and collect its usage metrics."""
    command = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
    ]
    if allowed_tools:
        command.extend(["--allowedTools", allowed_tools])
    if disallowed_tools:
        command.extend(["--disallowedTools", disallowed_tools])

    transcript_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - started
        return ClaudeRun(
            label=label,
            exit_code=124,
            wall_seconds=elapsed,
            error=f"timeout after {timeout_seconds} sec",
        )
    elapsed = time.perf_counter() - started

    transcript_path.write_text(completed.stdout, encoding="utf-8")

    run = parse_transcript(completed.stdout, label=label)
    run.exit_code = completed.returncode
    run.wall_seconds = elapsed
    run.transcript_path = str(transcript_path)
    if completed.returncode != 0 and not run.error:
        run.error = completed.stderr.strip()[:2000]

    return run


def parse_transcript(stdout: str, *, label: str) -> ClaudeRun:
    run = ClaudeRun(label=label, exit_code=0, wall_seconds=0.0)
    files: list[str] = []

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "assistant":
            _collect_tool_calls(event, run, files)
        elif event.get("type") == "result":
            _collect_result(event, run)

    run.files_touched = sorted(set(files))
    return run


def _collect_tool_calls(event: dict[str, Any], run: ClaudeRun, files: list[str]) -> None:
    for block in event.get("message", {}).get("content", []):
        if block.get("type") != "tool_use":
            continue

        name = str(block.get("name", "unknown"))
        run.tool_calls[name] = run.tool_calls.get(name, 0) + 1

        payload = block.get("input", {})
        if not isinstance(payload, dict):
            continue

        for key in ("file_path", "path", "notebook_path"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                files.append(value)

        if name == "Bash":
            command = payload.get("command")
            if isinstance(command, str):
                _collect_bash_command(command, run, files)


def _collect_bash_command(command: str, run: ClaudeRun, files: list[str]) -> None:
    """Count reads/searches issued through Bash and the files they name.

    Claude routinely batches `cat a b c` or loops over files, so one Bash call
    is counted once per read/search binary it invokes, not once per call.
    """
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
            run.bash_read_calls += 1
        elif binary in BASH_SEARCH_COMMANDS:
            run.bash_search_calls += 1
        else:
            continue

        files.extend(word for word in words[1:] if FILE_LIKE.match(word))


def _collect_result(event: dict[str, Any], run: ClaudeRun) -> None:
    usage = event.get("usage", {}) or {}

    run.input_tokens = int(usage.get("input_tokens", 0))
    run.cache_creation_input_tokens = int(usage.get("cache_creation_input_tokens", 0))
    run.cache_read_input_tokens = int(usage.get("cache_read_input_tokens", 0))
    run.output_tokens = int(usage.get("output_tokens", 0))

    run.cost_usd = float(event.get("total_cost_usd", 0.0) or 0.0)
    run.num_turns = int(event.get("num_turns", 0) or 0)
    run.duration_ms = int(event.get("duration_ms", 0) or 0)
    run.duration_api_ms = int(event.get("duration_api_ms", 0) or 0)
    run.model_usage = event.get("modelUsage", {}) or {}
    run.final_text = str(event.get("result", "") or "")

    denials = event.get("permission_denials", []) or []
    run.permission_denials = [
        str(item.get("tool_name", item)) if isinstance(item, dict) else str(item)
        for item in denials
    ]

    if event.get("is_error"):
        run.error = run.error or f"result subtype={event.get('subtype')}"
