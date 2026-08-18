import re
from pathlib import Path

from reposcout.executors.common import run_command
from reposcout.models import EvidenceResult, InvestigationQuery, SourceLocation

# rg's own match-line format with --line-number --with-filename:
# "path:line:content". Context lines (from --context) use "path-line-content"
# instead and are deliberately not parsed into locations below -- only an
# actual match is a confirmed location, not the surrounding context shown
# alongside it.
#
# The path group excludes ':' and whitespace: real file paths never contain
# either, and without that restriction a non-greedy ".+?" can walk past a
# context line's "-line-" separator into its content and false-match a
# coincidental "digit:digit" pattern deeper in the line (e.g. an ISO
# timestamp like "12:00:00" inside a matched JSON fixture), fabricating a
# SourceLocation with a bogus (or zero, which fails validation) line number.
_MATCH_LINE = re.compile(r"^(?P<path>[^:\s]+):(?P<line>\d+):")


def _match_locations(stdout: str) -> list[SourceLocation]:
    locations: list[SourceLocation] = []
    seen: set[tuple[str, int]] = set()
    for line in stdout.splitlines():
        match = _MATCH_LINE.match(line)
        if not match:
            continue
        key = (match.group("path"), int(match.group("line")))
        if key in seen:
            continue
        seen.add(key)
        locations.append(SourceLocation(path=key[0], start_line=key[1], end_line=key[1]))
    return locations


class RipgrepExecutor:
    # A match line alone is a locator, not evidence: multi-line constructs
    # (import blocks, signatures, decorators) routinely span past it. Bounded
    # context turns each match into a self-contained excerpt without an extra
    # LLM round-trip; rg merges overlapping/adjacent windows on its own.
    #
    # Applying context to every query blew Evidence up 8-10x on broad,
    # multi-file sweeps that didn't need it (CP5). A query scoped to a small,
    # explicit file set is asking "what does this look like here" and gets
    # context; a query fanning out across many files is asking "where is
    # this" and stays locator-only (CP5b).
    CONTEXT_LINES = 5
    NARROW_PATH_THRESHOLD = 3

    def execute(self, root: Path, query: InvestigationQuery) -> EvidenceResult:
        # --with-filename: rg omits the path prefix when given exactly one
        # file, which would make match lines unparseable into SourceLocation.
        command = ["rg", "--line-number", "--no-heading", "--with-filename"]
        if 0 < len(query.paths) <= self.NARROW_PATH_THRESHOLD:
            command.extend(["--context", str(self.CONTEXT_LINES)])
        command.append(query.pattern or "")
        command.extend(query.paths)

        code, stdout, stderr = run_command(root, command)
        if code in {0, 1}:
            return EvidenceResult(
                query_id=query.id,
                status="PASS",
                executor="ripgrep",
                evidence=stdout.strip(),
                source_locations=_match_locations(stdout),
            )

        return EvidenceResult(
            query_id=query.id,
            status="ERROR",
            executor="ripgrep",
            error=stderr.strip() or f"rg exited with code {code}",
        )
