"""Model-free acceptance checks against one task's EvidenceContract.

Reuses cp7_metrics.score_generic (unchanged) as the evaluator; nothing here
scores anything score_generic doesn't already define. The additional checks
(traceability, fictional paths, repo leaks, UNKNOWN handling) are the
deterministic properties Product Acceptance itself is verifying, not new
ground truth.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cp7_metrics import score_generic

from reposcout.models import EvidenceContract
from reposcout.scope import RepositoryFileScope


@dataclass(frozen=True)
class AcceptanceResult:
    task_key: str
    coverage: dict[str, Any]
    traceable_files: list[str]
    untraceable_files: list[str]
    fictional_paths: list[str]
    repo_leak_count: int
    unknown_count: int
    unresolved_count: int
    error_count: int
    evidence_chars: int
    source_location_count: int

    @property
    def required_evidence_present(self) -> bool:
        return self.coverage["coverage"] == 1.0

    @property
    def fully_traceable(self) -> bool:
        return not self.untraceable_files

    @property
    def passed(self) -> bool:
        return (
            self.required_evidence_present
            and self.fully_traceable
            and not self.fictional_paths
            and self.repo_leak_count == 0
        )


def _raw_evidence_text(contract: EvidenceContract) -> str:
    return "\n".join(item.evidence for item in contract.query_evidence)


def _traceability(contract: EvidenceContract, expected_files: list[str]) -> tuple[list, list]:
    paths = {location.path for location in contract.source_locations}
    traceable = [f for f in expected_files if any(p.endswith(f) for p in paths)]
    untraceable = [f for f in expected_files if f not in traceable]
    return traceable, untraceable


def _fictional_paths(contract: EvidenceContract, root: Path) -> list[str]:
    tracked = set(RepositoryFileScope().list_files(root))
    return sorted({loc.path for loc in contract.source_locations if loc.path not in tracked})


def _repo_leak_count(contract: EvidenceContract, root: Path) -> int:
    text = _raw_evidence_text(contract) + str([loc.path for loc in contract.source_locations])
    return text.count(str(root.resolve()))


def evaluate(task: dict[str, Any], contract: EvidenceContract, root: Path) -> AcceptanceResult:
    text = _raw_evidence_text(contract)
    coverage = score_generic(text, task)
    traceable, untraceable = _traceability(contract, task["expected_files"])

    return AcceptanceResult(
        task_key=task["key"],
        coverage=coverage,
        traceable_files=traceable,
        untraceable_files=untraceable,
        fictional_paths=_fictional_paths(contract, root),
        repo_leak_count=_repo_leak_count(contract, root),
        unknown_count=len(contract.unknown),
        unresolved_count=sum(1 for u in contract.unknown if u.status == "UNRESOLVED"),
        error_count=sum(1 for u in contract.unknown if u.status == "ERROR"),
        evidence_chars=len(text),
        source_location_count=len(contract.source_locations),
    )
