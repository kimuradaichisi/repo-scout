"""Decision Identity: what Main actually decided, recorded canonically.

decision_count == 1 only says the task asked for one judgement. It does not
say the judgement that came back was the same one at every size, and if S and
L resolved the design differently then they are not two points on one
execution-volume axis -- they are two different problems whose costs happen to
be plotted next to each other.

So every run is required to emit a DECISION RECORD with four fixed axes, and
each axis is mapped to a canonical category by keyword, deterministically and
by a rule fixed before any run. The raw sentence is always kept beside the
category: the classifier is coarse on purpose, and a reader has to be able to
see when it was the classifier that was wrong rather than the run.

Classification fails closed. An axis whose sentence matches no category or
matches two becomes UNCLEAR, and an UNCLEAR axis is never treated as
"equivalent" to anything -- including another UNCLEAR. Comparing two sizes we
could not read is exactly the case this module exists to refuse.
"""

import re
from dataclasses import dataclass
from typing import Any

DECISION_AXES = (
    "domain_model_representation",
    "measurement_responsibility",
    "compatibility_strategy",
    "propagation_strategy",
)

AXIS_LABELS = {
    "domain_model_representation": "DOMAIN MODEL REPRESENTATION",
    "measurement_responsibility": "MEASUREMENT RESPONSIBILITY",
    "compatibility_strategy": "COMPATIBILITY STRATEGY",
    "propagation_strategy": "PROPAGATION STRATEGY",
}

UNCLEAR = "UNCLEAR"

# Fixed before Step 0.5. Each category is a tuple of regexes; a sentence
# belongs to a category when any of them matches.
CATEGORY_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "domain_model_representation": {
        "evidence_result_field": (r"evidenceresult",),
        "separate_model": (r"別\s*の?\s*モデル", r"new model", r"separate model", r"別クラス"),
        "outside_domain_model": (r"ドメインモデル(に|には)\s*(置か|持たせ)", r"outside the domain"),
    },
    "measurement_responsibility": {
        "executor_measures": (
            r"各\s*executor",
            r"executor\s*が\s*(自分で)?\s*計測",
            r"in each executor",
        ),
        "common_helper": (r"run_command", r"共通\s*ヘルパ", r"common\.py", r"shared helper"),
        "runner_measures": (r"queryrunner", r"investigationrunner", r"runner\s*が\s*計測"),
    },
    "compatibility_strategy": {
        "optional_default": (
            r"省略可能",
            r"既定値",
            r"default",
            r"optional",
            r"none\b",
            r"\|\s*none",
        ),
        "required_field": (r"必須", r"required", r"全\s*構築\s*箇所"),
    },
    "propagation_strategy": {
        "all_sites": (r"全\s*executor", r"一律", r"repository-wide", r"リポジトリ全体"),
        "listed_only": (r"列挙", r"対象のみ", r"listed", r"in scope only", r"スコープ内のみ"),
    },
}


@dataclass(frozen=True)
class DecisionRecord:
    raw: dict[str, str]
    categories: dict[str, str]

    @property
    def complete(self) -> bool:
        return all(self.raw.get(axis, "").strip() for axis in DECISION_AXES)

    @property
    def readable(self) -> bool:
        return all(self.categories.get(axis) != UNCLEAR for axis in DECISION_AXES)


def _axis_line(text: str, label: str) -> str:
    """The one-liner following `label:` in the report, if present."""
    pattern = re.compile(rf"^\s*[-*]?\s*{re.escape(label)}\s*[:：]\s*(.+)$", re.MULTILINE | re.I)
    found = pattern.search(text)
    return found.group(1).strip() if found else ""


def classify(axis: str, sentence: str) -> str:
    """One category, or UNCLEAR when no pattern or more than one matches."""
    if not sentence.strip():
        return UNCLEAR
    lowered = sentence.lower()
    hits = [
        category
        for category, patterns in CATEGORY_PATTERNS[axis].items()
        if any(re.search(pattern, lowered) for pattern in patterns)
    ]
    return hits[0] if len(hits) == 1 else UNCLEAR


def parse_decision_record(report_text: str) -> DecisionRecord:
    raw = {axis: _axis_line(report_text, AXIS_LABELS[axis]) for axis in DECISION_AXES}
    categories = {axis: classify(axis, raw[axis]) for axis in DECISION_AXES}
    return DecisionRecord(raw=raw, categories=categories)


def compare(left: DecisionRecord, right: DecisionRecord) -> dict[str, Any]:
    """Axis-by-axis identity. UNCLEAR never counts as a match."""
    per_axis = {
        axis: {
            "left_category": left.categories[axis],
            "right_category": right.categories[axis],
            "left_raw": left.raw[axis],
            "right_raw": right.raw[axis],
            "same": (
                left.categories[axis] == right.categories[axis] and left.categories[axis] != UNCLEAR
            ),
        }
        for axis in DECISION_AXES
    }
    return {
        "per_axis": per_axis,
        "both_complete": left.complete and right.complete,
        "both_readable": left.readable and right.readable,
        "identical": all(entry["same"] for entry in per_axis.values()),
        "matching_axis_count": sum(1 for entry in per_axis.values() if entry["same"]),
    }


def record_summary(record: DecisionRecord) -> dict[str, Any]:
    return {
        "raw": dict(record.raw),
        "categories": dict(record.categories),
        "complete": record.complete,
        "readable": record.readable,
    }
