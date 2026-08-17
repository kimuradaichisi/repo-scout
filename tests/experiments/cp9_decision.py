"""Decision Identity as canonical enums, not as prose to be classified.

The first Step 0.5 failed C3 on two axes where S and L had in fact decided the
same thing. One run answered in English and one in Japanese, and the keyword
classifier's patterns were Japanese-shaped, so "Each executor measures its own
span" matched nothing and became UNCLEAR. On the other axis the classifier
matched the phrase "repository-wide" in a clause that was describing the model
field, not the propagation. Both failures were the instrument reading the
sentence, and no amount of extra patterns fixes a scheme whose input is free
text in an unconstrained language.

So the run now emits the category itself. Each axis is one line carrying one
value copied from a closed list, and identity is exact equality of those
values -- nothing is inferred from wording, and the same decision written in
either language produces the same token. The rationale is still collected and
still stored, but it is audit material for a human reading the artifact; it
never reaches the comparison.

Fail-closed is unchanged: an unknown value, a missing axis, or more than one
value on a line is INVALID, and INVALID is never equal to anything, including
another INVALID.
"""

import re
from dataclasses import dataclass
from typing import Any

DECISION_ENUMS: dict[str, tuple[str, ...]] = {
    "domain_model_representation": (
        "evidence_result_field",
        "separate_model",
        "outside_domain_model",
    ),
    "measurement_responsibility": (
        "executor_measures",
        "common_helper",
        "runner_measures",
    ),
    "compatibility_strategy": ("optional_default", "required_field"),
    "propagation_strategy": ("all_sites", "listed_only"),
}

DECISION_AXES = tuple(DECISION_ENUMS)
INVALID = "INVALID"

# Stripped before matching so a value in backticks or with a trailing period is
# still read as the token it plainly is. Anything beyond that is INVALID.
_TRIM = " \t`'\"。."
_RATIONALE = re.compile(r"^\s*RATIONALE\s*[:：]\s*(.*)$", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class DecisionRecord:
    values: dict[str, str]
    rationale: str
    raw_lines: dict[str, str]

    @property
    def valid(self) -> bool:
        return all(self.values.get(axis, INVALID) != INVALID for axis in DECISION_AXES)


def _axis_line(text: str, axis: str) -> str:
    pattern = re.compile(rf"^\s*[-*]?\s*{re.escape(axis)}\s*[:：]\s*(.*)$", re.MULTILINE | re.I)
    found = pattern.search(text)
    return found.group(1).strip() if found else ""


def read_value(axis: str, line: str) -> str:
    """Exactly one enum token, or INVALID.

    A missing line, an unknown token, added prose and two tokens on one line
    all land in the same place, because none of them is the run stating one
    category unambiguously.
    """
    candidate = line.strip().strip(_TRIM).lower()
    return candidate if candidate in DECISION_ENUMS[axis] else INVALID


def parse_decision_record(report_text: str) -> DecisionRecord:
    raw_lines = {axis: _axis_line(report_text, axis) for axis in DECISION_AXES}
    values = {axis: read_value(axis, raw_lines[axis]) for axis in DECISION_AXES}
    found = _RATIONALE.search(report_text)
    return DecisionRecord(
        values=values, rationale=found.group(1).strip() if found else "", raw_lines=raw_lines
    )


def compare(left: DecisionRecord, right: DecisionRecord) -> dict[str, Any]:
    """Axis-by-axis exact equality of enum values. INVALID never matches."""
    per_axis = {
        axis: {
            "left": left.values[axis],
            "right": right.values[axis],
            "same": left.values[axis] == right.values[axis] and left.values[axis] != INVALID,
        }
        for axis in DECISION_AXES
    }
    return {
        "per_axis": per_axis,
        "both_valid": left.valid and right.valid,
        "identical": all(entry["same"] for entry in per_axis.values()),
        "matching_axis_count": sum(1 for entry in per_axis.values() if entry["same"]),
    }


def record_summary(record: DecisionRecord) -> dict[str, Any]:
    return {
        "values": dict(record.values),
        "valid": record.valid,
        "raw_lines": dict(record.raw_lines),
        "rationale": record.rationale,
        "rationale_used_for_scoring": False,
    }


def allowed_values_block() -> str:
    """The closed list, rendered for the prompt so both sides read one source."""
    return "\n".join(f"{axis}: {' | '.join(values)}" for axis, values in DECISION_ENUMS.items())
