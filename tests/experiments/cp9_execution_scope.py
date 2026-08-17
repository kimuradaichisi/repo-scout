"""Execution Scope: the part of a CP9 run that is supposed to differ by size.

This is the other half of the v3 split. Decision Identity holds the judgement
constant and gates C3; Execution Scope records how much of the repository that
judgement was applied to, and gates nothing. S, M and L differing here is not
a finding, it is the independent variable doing its job -- which is exactly
what v2's fourth Decision Identity axis got wrong.

`propagation_strategy` lives here now. It is still asked for, still parsed,
still stored per run; it simply sits beside the target list and the volume
vector, where a reader can see it for what it is: the run's own description of
the scope it was given, not a design choice it was free to make differently at
the same size.
"""

from typing import Any

VOLUME_KEYS = {
    "v1": "v1_planned_atomic_changes",
    "v2": "v2_required_edit_sites",
    "v3": "v3_required_new_files",
    "v4": "v4_required_test_cases",
    "v5": "v5_required_verification_cycles",
}


def volume_vector(task: dict[str, Any]) -> dict[str, int]:
    return {label: int(task["volume"][key]) for key, label in VOLUME_KEYS.items()}


def execution_scope(task: dict[str, Any], record: Any = None) -> dict[str, Any]:
    """Everything about this run that is meant to vary with size.

    `record` is the run's DecisionRecord when one is available; its
    propagation_strategy is copied in as a declaration. Absent it, the scope is
    still fully described by the task definition alone, which is the point: the
    scope is fixed before the run, not discovered from it.
    """
    scope: dict[str, Any] = {
        "size": task["size"],
        "task_key": task["key"],
        "target_list": list(task["targets"]),
        "target_count": len(task["targets"]),
        "allowed_paths": list(task["allowed_paths"]),
        "allowed_path_count": len(task["allowed_paths"]),
        "forbidden_paths": list(task["forbidden_paths"]),
        "volume": volume_vector(task),
        "used_for_decision_identity": False,
    }
    declared = getattr(record, "scope_declaration", None)
    scope["declared_propagation_strategy"] = (
        declared.get("propagation_strategy") if isinstance(declared, dict) else None
    )
    return scope


def scope_differences(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """How two sizes differ. Reported for the record; never a pass/fail input."""
    volumes = {
        label: {"left": left["volume"][label], "right": right["volume"][label]}
        for label in VOLUME_KEYS.values()
    }
    return {
        "sizes": [left["size"], right["size"]],
        "allowed_path_count": [left["allowed_path_count"], right["allowed_path_count"]],
        "volume": volumes,
        "declared_propagation_strategy": [
            left["declared_propagation_strategy"],
            right["declared_propagation_strategy"],
        ],
        "differs_by_design": True,
        "used_for_axis_validity": False,
    }
