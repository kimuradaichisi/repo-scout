"""The Implementation Pack and Result Pack contracts.

The Pack is the whole experiment in one artifact: it is the only thing that
crosses from Main to the Worker, so whatever Main knows and does not write
down is knowledge the Worker must go and rediscover. CP7-H found the same
shape on the reporting side -- one fact, stated once, with its source -- and
the Pack keeps to it: a decision is recorded with its reason, and evidence is
recorded with the location it came from.

RELEVANT EVIDENCE and TARGET FILES are also what cp8_worker_metrics.py reads
to decide whether a Worker read was directed by the Pack or was the Worker
going looking on its own, so the paths in them have to be real paths.
"""

import re

IMPLEMENTATION_PACK_SECTIONS = (
    "GOAL",
    "DECISIONS",
    "WHY",
    "TARGET FILES",
    "REQUIRED CHANGES",
    "DO NOT CHANGE",
    "ACCEPTANCE CRITERIA",
    "RELEVANT EVIDENCE",
)

RESULT_PACK_SECTIONS = (
    "CHANGED FILES",
    "IMPLEMENTED CHANGES",
    "TEST RESULTS",
    "QUALITY GATE RESULTS",
    "DEVIATIONS",
    "UNKNOWN / BLOCKED",
)

IMPLEMENTATION_PACK_TEMPLATE = """\
Write the Implementation Pack using exactly these headings, in this order, and
nothing outside them. The Worker sees this text and no part of your
investigation, so anything you leave out is something it will have to go and
find again -- or guess.

## GOAL
What the finished change accomplishes, in one or two sentences.

## DECISIONS
The design choices you have already made and settled. One per line. The Worker
implements these; it does not revisit them.

## WHY
The reason behind each decision above, tied to what you found in the
repository. A decision without a reason invites the Worker to re-litigate it.

## TARGET FILES
One repository-relative path per line, with what happens to it (new file,
edited, test added). Only paths that may be touched.

## REQUIRED CHANGES
Per target file, what must change, precisely enough to implement without
rereading the surrounding subsystem.

## DO NOT CHANGE
Files, symbols, and behaviours that must be left exactly as they are, and
anything you considered changing and decided against.

## ACCEPTANCE CRITERIA
The conditions under which the change is complete, each one checkable. Include
the quality gates the repository requires.

## RELEVANT EVIDENCE
The facts from your investigation the Worker needs, each with the location it
came from (`path:line`). Copy the evidence; do not summarise it away.
"""

RESULT_PACK_SPEC = """\
## CHANGED FILES
## IMPLEMENTED CHANGES
## TEST RESULTS
## QUALITY GATE RESULTS
## DEVIATIONS
## UNKNOWN / BLOCKED
"""

_HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s*|\*\*\s*)?([A-Z][A-Z /]+)\s*(?:\*\*)?\s*:?\s*$", re.M)
_PATH = re.compile(r"[\w./-]+\.(?:py|md|toml|lock|yaml|yml|sh)\b")


def split_sections(text: str, sections: tuple[str, ...]) -> dict[str, str]:
    """Split a Pack into its declared sections; absent ones stay absent."""
    matches = [m for m in _HEADING.finditer(text) if m.group(1).strip() in sections]
    found: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        found[match.group(1).strip()] = text[match.end() : end].strip()
    return found


def missing_sections(text: str, sections: tuple[str, ...]) -> list[str]:
    found = split_sections(text, sections)
    return [name for name in sections if name not in found]


def extract_pack_paths(pack_text: str) -> frozenset[str]:
    """Paths the Pack directed the Worker at: TARGET FILES + RELEVANT EVIDENCE.

    A read of anything else is the Worker exploring rather than following, which
    is what worker_outside_pack_read_count is counting.
    """
    sections = split_sections(pack_text, IMPLEMENTATION_PACK_SECTIONS)
    scoped = " ".join(sections.get(name, "") for name in ("TARGET FILES", "RELEVANT EVIDENCE"))
    return frozenset(_PATH.findall(scoped))
