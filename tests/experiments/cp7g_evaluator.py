"""Evaluator v2 for the CP7-G Result Contract experiment.

v1 scored one string — the whole final answer — with a strict substring
match, so a semantically complete answer that named a symbol by file and line
instead of by name scored as incomplete (CP7-F change_scope). v2 does not
replace that number; it adds two more so the three questions it conflated can
be read apart:

    evidence_coverage          did RepoScout retrieve the ground truth at all?
    structured_answer_coverage did the answer state it in a section whose
                               wording the contract constrains?
    legacy_lexical_coverage    the v1 number, computed exactly as before.

Reading them together localizes a failure: evidence_coverage < 1 is a
retrieval failure, structured < 1 with evidence 1.0 is a reporting failure,
and legacy < structured is wording sensitivity rather than a real gap.

The matching rule itself is unchanged — all three delegate to
cp7_metrics.score_generic — so v2 changes what text is scored, never how.
"""

import hashlib
import re
from pathlib import Path
from typing import Any

from cp7_metrics import score_generic
from prompts import V2_ALL_SECTIONS, V2_CANONICAL_SECTIONS

# Matches "## FACTS", "**FACTS**", "FACTS" at line start — the contract fixes
# the heading text, not its markdown decoration.
_SECTION_NAMES = "|".join(re.escape(name) for name in V2_ALL_SECTIONS)
SECTION_HEADING = re.compile(
    rf"^\s{{0,3}}(?:#{{1,6}}\s*|\*\*\s*)?({_SECTION_NAMES})\s*(?:\*\*)?\s*:?\s*$",
    re.MULTILINE,
)


def evidence_sha256(evidence_path: Path) -> str:
    """Hash of the stored Evidence body, to prove a replay reused it verbatim."""
    return hashlib.sha256(evidence_path.read_bytes()).hexdigest()


def split_sections(answer: str) -> dict[str, str]:
    """Split a v2 answer into its contract sections.

    Sections the answer omitted are absent from the result rather than empty,
    so a missing section and an empty one stay distinguishable.
    """
    matches = list(SECTION_HEADING.finditer(answer))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        sections[match.group(1)] = answer[match.end() : end].strip()
    return sections


def canonical_text(sections: dict[str, str]) -> str:
    """The machine-scored slice of the answer: canonical sections only.

    SUMMARY is excluded by V2_CANONICAL_SECTIONS -- it is the section allowed
    to paraphrase, so scoring it would restore the v1 wording sensitivity.
    """
    return "\n".join(sections.get(name, "") for name in V2_CANONICAL_SECTIONS)


def evaluate(answer: str, evidence: str, task: dict[str, Any]) -> dict[str, Any]:
    """Score one answer three ways against a task's unchanged ground truth."""
    sections = split_sections(answer)

    evidence_detail = score_generic(evidence, task)
    structured_detail = score_generic(canonical_text(sections), task)
    legacy_detail = score_generic(answer, task)

    return {
        "evidence_coverage": evidence_detail["coverage"],
        "structured_answer_coverage": structured_detail["coverage"],
        "legacy_lexical_coverage": legacy_detail["coverage"],
        "evidence_detail": evidence_detail,
        "structured_detail": structured_detail,
        "legacy_detail": legacy_detail,
        "sections_present": [name for name in V2_ALL_SECTIONS if name in sections],
        "sections_missing": [name for name in V2_ALL_SECTIONS if name not in sections],
        "contract_satisfied": all(name in sections for name in V2_ALL_SECTIONS),
        "section_chars": {name: len(body) for name, body in sections.items()},
        "mentions_test_gap": legacy_detail["mentions_test_gap"],
        "answer_chars": len(answer),
    }
