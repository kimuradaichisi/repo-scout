"""Decision Identity (CP9-v3): the three axes that must not vary with size.

v2 compared four axes and failed C3 on `propagation_strategy`, with S saying
`listed_only` and L saying `all_sites`. The instrument was working -- both
records parsed cleanly, no INVALID -- and the runs had behaved identically:
each changed exactly its allowed paths and nothing else. What differed was the
label, because at L the enumerated list happens to be every executor, so both
words describe the same act truthfully.

That made the fourth axis a restatement of the independent variable. S/M/L are
*defined* by how many sites the decision is applied to, so requiring
propagation to be constant across sizes was requiring the size not to vary.
v3 draws the line where it belongs:

    Decision Identity   fixed across sizes, gates C3   (3 axes, here)
    Execution Scope     varies by design, never gates  (cp9_execution_scope)

The value is still collected -- the prompt is unchanged and still asks for all
four lines -- it is simply recorded as a scope declaration rather than scored
as a decision. Nothing is dropped; the boundary moved.

Fail-closed is unchanged from v2: unknown value, missing line, or two values
on one line is INVALID, and INVALID never equals anything, including another
INVALID.
"""

import re
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = "cp9-v3"

# Gated by C3. Identical values required at every size.
IDENTITY_ENUMS: dict[str, tuple[str, ...]] = {
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
}

# Collected, reported, never gated. Differing across sizes is the correct state.
SCOPE_DECLARATION_ENUMS: dict[str, tuple[str, ...]] = {
    "propagation_strategy": ("all_sites", "listed_only"),
}

ALL_ENUMS = {**IDENTITY_ENUMS, **SCOPE_DECLARATION_ENUMS}
IDENTITY_AXES = tuple(IDENTITY_ENUMS)
SCOPE_AXES = tuple(SCOPE_DECLARATION_ENUMS)
INVALID = "INVALID"

# Stripped before matching so a value in backticks or with a trailing period is
# still read as the token it plainly is. Anything beyond that is INVALID.
_TRIM = " \t`'\"。."
_RATIONALE = re.compile(r"^\s*RATIONALE\s*[:：]\s*(.*)$", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class DecisionRecord:
    identity: dict[str, str]
    scope_declaration: dict[str, str]
    rationale: str
    raw_lines: dict[str, str]

    @property
    def valid(self) -> bool:
        """Readable on the three gated axes. A scope declaration never decides this."""
        return all(self.identity.get(axis, INVALID) != INVALID for axis in IDENTITY_AXES)


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
    return candidate if candidate in ALL_ENUMS[axis] else INVALID


def parse_decision_record(report_text: str) -> DecisionRecord:
    raw_lines = {axis: _axis_line(report_text, axis) for axis in ALL_ENUMS}
    found = _RATIONALE.search(report_text)
    return DecisionRecord(
        identity={axis: read_value(axis, raw_lines[axis]) for axis in IDENTITY_AXES},
        scope_declaration={axis: read_value(axis, raw_lines[axis]) for axis in SCOPE_AXES},
        rationale=found.group(1).strip() if found else "",
        raw_lines=raw_lines,
    )


def compare(left: DecisionRecord, right: DecisionRecord) -> dict[str, Any]:
    """Exact equality over the three identity axes. Scope declarations are ignored."""
    per_axis = {
        axis: {
            "left": left.identity[axis],
            "right": right.identity[axis],
            "same": left.identity[axis] == right.identity[axis] and left.identity[axis] != INVALID,
        }
        for axis in IDENTITY_AXES
    }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "per_axis": per_axis,
        "both_valid": left.valid and right.valid,
        "identical": all(entry["same"] for entry in per_axis.values()),
        "matching_axis_count": sum(1 for entry in per_axis.values() if entry["same"]),
        "axis_count": len(IDENTITY_AXES),
        "scope_declaration_left": dict(left.scope_declaration),
        "scope_declaration_right": dict(right.scope_declaration),
        "scope_declaration_used_for_identity": False,
    }


def record_summary(record: DecisionRecord) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "identity": dict(record.identity),
        "identity_valid": record.valid,
        "scope_declaration": dict(record.scope_declaration),
        "raw_lines": dict(record.raw_lines),
        "rationale": record.rationale,
        "rationale_used_for_scoring": False,
    }


def allowed_values_block() -> str:
    """The closed lists, rendered for the prompt so both sides read one source.

    All four axes are rendered: the prompt is unchanged from v2, and the run is
    still asked for the propagation line. Only what the harness does with that
    line changed.
    """
    return "\n".join(f"{axis}: {' | '.join(values)}" for axis, values in ALL_ENUMS.items())
