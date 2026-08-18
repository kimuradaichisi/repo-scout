"""RepoScout 1.0 Product Acceptance -- deterministic queries for CP7's three tasks.

Ground truth (expected_files/expected_symbols/expected_extended,
investigation_goal) is cp7_tasks.py's -- imported, never redefined or
modified. Queries here are hand-authored rg/read lookups that search for
exactly those already-fixed expected terms plus each task's own named
investigation target; nothing new is being scored, only how it is retrieved.

One instruction-only, tool-unset query is included per task (an
"unresolved slot") to exercise the UNRESOLVED path deterministically within
the acceptance run itself, rather than only trusting unit test coverage of
that behavior. It carries no expected terms and is not scored.
"""

from reposcout.models import InvestigationQuery, QueryTool

SCOPE_PATHS = ["src", "tests/unit"]


def _rg(query_id: str, pattern: str) -> InvestigationQuery:
    return InvestigationQuery(id=query_id, tool=QueryTool.RG, pattern=pattern, paths=SCOPE_PATHS)


def _read(query_id: str, file: str) -> InvestigationQuery:
    return InvestigationQuery(id=query_id, tool=QueryTool.READ, file=file)


def _unresolved_slot(query_id: str) -> InvestigationQuery:
    return InvestigationQuery(
        id=query_id, instruction="reserved slot for explicit semantic exploration, unused here"
    )


TASK_QUERIES: dict[str, list[InvestigationQuery]] = {
    "symbol_impact": [
        _rg("Q1", "EvidenceWriter"),
        _rg("Q2", "write_plan"),
        _rg("Q3", "write_result"),
        _rg("Q4", "write_pack"),
        _rg("Q5", "InvestigationRunner"),
        _rg("Q6", "InvestigationPlan"),
        _rg("Q7", "EvidenceResult"),
        _read("Q8", "src/reposcout/evidence.py"),
        _unresolved_slot("Q9"),
    ],
    "behavior_localization": [
        _rg("Q1", "QueryRunner"),
        _rg("Q2", "OrnithWorker"),
        _rg("Q3", "_executors"),
        _rg("Q4", "SYSTEM_PROMPT"),
        _rg("Q5", "subprocess"),
        _read("Q6", "src/reposcout/runner.py"),
        _read("Q7", "src/reposcout/ornith/client.py"),
        _unresolved_slot("Q8"),
    ],
    "change_scope": [
        _rg("Q1", "CONTEXT_LINES"),
        _rg("Q2", "NARROW_PATH_THRESHOLD"),
        _rg("Q3", "RipgrepExecutor"),
        _rg("Q4", "QueryRunner"),
        _read("Q5", "src/reposcout/executors/ripgrep.py"),
        _unresolved_slot("Q6"),
    ],
}
