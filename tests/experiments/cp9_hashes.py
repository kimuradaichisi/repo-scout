"""Fixed conditions for a CP9 run: the snapshot's, plus CP9's own definitions.

CP8 hashed what lived inside the snapshot -- the coding rules, the Worker
definition, the hooks, the RepoScout adapter -- because those are what a run
could in principle have altered. CP9 keeps all of that unchanged and reuses
the same template files, so those hashes should match CP8's exactly, and a
mismatch means the shared infrastructure moved rather than CP9 diverging.

CP9 adds a second set. Its task sizes, acceptance criteria, prompts, decision
axes and gate thresholds all have to be fixed before Step 0.5 and stay fixed
through Step 1, and they live in the harness rather than the snapshot, where
no per-run hash would otherwise notice them changing. Hashing them is what
makes "the sizes were not retuned after seeing the results" checkable instead
of asserted.
"""

from pathlib import Path
from typing import Any

from cp8_hashes import environment_record, sha256_file

# Relative to tests/experiments. Changing any of these invalidates comparison
# against runs recorded under the previous hash.
CP9_DEFINITION_FILES = {
    "cp9_tasks": "cp9_tasks.py",
    "cp9_prompts": "cp9_prompts.py",
    "cp9_decision": "cp9_decision.py",
    "cp9_axis_gate": "cp9_axis_gate.py",
    "cp9_telemetry": "cp9_telemetry.py",
    "cp9_gates": "cp9_gates.py",
    "cp9_scope": "cp9_scope.py",
}

LOCKED_HASHES_PATH = "results/cp9-fixed-infrastructure/locked-hashes.json"


def cp9_definition_hashes(experiments_dir: Path) -> dict[str, str]:
    return {
        name: sha256_file(experiments_dir / relative)
        for name, relative in CP9_DEFINITION_FILES.items()
    }


def cp9_environment_record(snapshot: Path, experiments_dir: Path) -> dict[str, Any]:
    record = environment_record(snapshot)
    record["cp9_definition_hashes"] = cp9_definition_hashes(experiments_dir)
    return record
