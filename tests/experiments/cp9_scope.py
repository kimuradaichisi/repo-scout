"""Scope measured against what the task allowed, not against what it forbade.

CP9's first Step 0.5 exposed why a forbidden-prefix list cannot be the primary
scope metric here. The list shrinks as the task grows -- S forbids six paths,
L forbids two, because L is meant to touch nearly everything -- so the metric
has most of its power at exactly the size where the least work happens, and
almost none where the most does. The two sizes were not measuring the same
thing, and CP9 compares across sizes.

An allowlist inverts that. `allowed_paths` is fixed in the task definition
before any run and is the same idea at every size: anything else left in the
repository is a violation, whether it is a source file the run should not have
touched or a scratch file it could not delete. The count means the same thing
at S and at L even though the lists differ in length.

Nothing here removes anything. Cleaning the working tree before measuring it
would be the harness deciding what the result should be.
"""

from typing import Any


def scope_violations(changed_paths: list[str], task: dict[str, Any]) -> list[str]:
    """Changed repository paths the task did not declare as targets."""
    allowed = set(task["allowed_paths"])
    return sorted(path for path in changed_paths if path not in allowed)


def missing_targets(changed_paths: list[str], task: dict[str, Any]) -> list[str]:
    """Declared targets that were never changed. Contract conformance, not scope."""
    changed = set(changed_paths)
    return sorted(path for path in task["allowed_paths"] if path not in changed)


def scope_report(changed_paths: list[str], task: dict[str, Any]) -> dict[str, Any]:
    violations = scope_violations(changed_paths, task)
    missing = missing_targets(changed_paths, task)
    return {
        "allowed_paths": list(task["allowed_paths"]),
        "allowed_path_count": len(task["allowed_paths"]),
        "changed_paths": sorted(changed_paths),
        "scope_violation_paths": violations,
        "scope_violation_count": len(violations),
        "missing_target_paths": missing,
        "expected_files_present": not missing,
    }
