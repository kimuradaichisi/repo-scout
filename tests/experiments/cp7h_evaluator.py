"""Evaluator for CP7-H's Compact Structured Result Contract (v3).

v2 (cp7g_evaluator.py) split an answer into FACTS / RELATIONS / SOURCE
LOCATIONS and scored the union of those three. v3 collapses them into one
CLAIMS section -- each claim already carries its own source -- so there is
only one canonical section to extract and score. The matcher itself
(score_generic, imported from cp7_metrics) is untouched: v3 changes what
text is scored, never how, same as v2 did.

This module is independent of cp7g_evaluator.py rather than importing from
it, so CP7-G's already-committed evaluator and its recorded result stay
exactly as they were run.
"""

import re
from dataclasses import dataclass
from typing import Any

import yaml
from cp7_metrics import score_generic
from prompts import V3_ALL_SECTIONS, V3_CANONICAL_SECTIONS, V3_SUMMARY_MAX_CHARS

_SECTION_NAMES = "|".join(re.escape(name) for name in V3_ALL_SECTIONS)
SECTION_HEADING = re.compile(
    rf"^\s{{0,3}}(?:#{{1,6}}\s*|\*\*\s*)?({_SECTION_NAMES})\s*(?:\*\*)?\s*:?\s*$",
    re.MULTILINE,
)

_CLAIM_LINE = re.compile(r"^\s*-\s*subject\s*:\s*(.+)$", re.IGNORECASE)
_FIELD_LINE = re.compile(r"^\s*(subject|predicate|object|source)\s*:\s*(.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class Claim:
    subject: str
    predicate: str
    object: str
    source: str
    raw: str


def split_sections(answer: str) -> dict[str, str]:
    """Split a v3 answer into its contract sections (present sections only)."""
    matches = list(SECTION_HEADING.finditer(answer))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        sections[match.group(1)] = answer[match.end() : end].strip()
    return sections


def parse_claims(claims_text: str) -> list[Claim]:
    """Parse the CLAIMS section into structured claims.

    Tries YAML first (the prompt asks for a YAML-shaped list); falls back to
    line-scanning on "- subject:" boundaries so a near-miss format (e.g. a
    stray blank line YAML chokes on) still yields claims for the duplicate
    and coverage-detail counts in the report, rather than silently
    contributing zero claims to those counts.
    """
    claims = _parse_claims_yaml(claims_text)
    if claims is not None:
        return claims
    return _parse_claims_by_line(claims_text)


def _parse_claims_yaml(text: str) -> list[Claim] | None:
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, list):
        return None
    claims = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        claims.append(
            Claim(
                subject=str(item.get("subject", "")).strip(),
                predicate=str(item.get("predicate", "")).strip(),
                object=str(item.get("object", "")).strip(),
                source=str(item.get("source", "")).strip(),
                raw=str(item),
            )
        )
    return claims


def _parse_claims_by_line(text: str) -> list[Claim]:
    claims: list[Claim] = []
    fields: dict[str, str] = {}
    raw_lines: list[str] = []

    def flush() -> None:
        if fields:
            claims.append(
                Claim(
                    subject=fields.get("subject", ""),
                    predicate=fields.get("predicate", ""),
                    object=fields.get("object", ""),
                    source=fields.get("source", ""),
                    raw="\n".join(raw_lines),
                )
            )

    for line in text.splitlines():
        if _CLAIM_LINE.match(line):
            flush()
            fields = {}
            raw_lines = []
        match = _FIELD_LINE.match(line)
        if match:
            fields[match.group(1).lower()] = match.group(2).strip()
            raw_lines.append(line)
    flush()
    return claims


def duplicate_claim_count(claims: list[Claim]) -> int:
    """How many claims repeat a (subject, predicate, object) already seen."""
    seen: set[tuple[str, str, str]] = set()
    duplicates = 0
    for claim in claims:
        key = (claim.subject.lower(), claim.predicate.lower(), claim.object.lower())
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def matching_claims(claims: list[Claim], task: dict[str, Any]) -> list[Claim]:
    """Claims whose subject/object/source mentions a ground-truth item."""
    expected = [
        item.lower()
        for item in task["expected_files"]
        + task["expected_symbols"]
        + task.get("expected_extended", [])
    ]
    matched = []
    for claim in claims:
        haystack = f"{claim.subject} {claim.object} {claim.source}".lower()
        if any(item in haystack for item in expected):
            matched.append(claim)
    return matched


def canonical_text(sections: dict[str, str]) -> str:
    """The machine-scored slice: CLAIMS only (V3_CANONICAL_SECTIONS)."""
    return "\n".join(sections.get(name, "") for name in V3_CANONICAL_SECTIONS)


def evaluate(answer: str, evidence: str, task: dict[str, Any]) -> dict[str, Any]:
    """Score one v3 answer: evidence / compact-structured / legacy-lexical."""
    sections = split_sections(answer)
    claims_text = canonical_text(sections)
    claims = parse_claims(claims_text)

    evidence_detail = score_generic(evidence, task)
    structured_detail = score_generic(claims_text, task)
    legacy_detail = score_generic(answer, task)

    summary = sections.get("SUMMARY", "")

    return {
        "evidence_coverage": evidence_detail["coverage"],
        "compact_structured_coverage": structured_detail["coverage"],
        "legacy_lexical_coverage": legacy_detail["coverage"],
        "evidence_detail": evidence_detail,
        "structured_detail": structured_detail,
        "legacy_detail": legacy_detail,
        "sections_present": [name for name in V3_ALL_SECTIONS if name in sections],
        "sections_missing": [name for name in V3_ALL_SECTIONS if name not in sections],
        "contract_satisfied": all(name in sections for name in V3_ALL_SECTIONS),
        "section_chars": {name: len(body) for name, body in sections.items()},
        "claims_total": len(claims),
        "claims_duplicate": duplicate_claim_count(claims),
        "claims_matching_ground_truth": [
            {"subject": c.subject, "predicate": c.predicate, "object": c.object, "source": c.source}
            for c in matching_claims(claims, task)
        ],
        "summary_chars": len(summary),
        "summary_within_limit": len(summary) <= V3_SUMMARY_MAX_CHARS,
        "mentions_test_gap": legacy_detail["mentions_test_gap"],
        "answer_chars": len(answer),
    }
