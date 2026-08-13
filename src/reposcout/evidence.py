import json
from pathlib import Path

import yaml

from reposcout.models import EvidenceResult, InvestigationPlan, InvestigationQuery


class EvidenceWriter:
    def write_plan(self, run_dir: Path, plan: InvestigationPlan) -> None:
        payload = plan.model_dump(mode="json", exclude_none=True)
        (run_dir / "plan.yaml").write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def write_result(self, run_dir: Path, result: EvidenceResult) -> None:
        path = run_dir / f"{result.query_id}.json"
        path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def write_pack(
        self,
        run_dir: Path,
        plan: InvestigationPlan,
        results: list[EvidenceResult],
    ) -> None:
        sections = [
            "# Investigation Evidence",
            "",
            "## Goal",
            "",
            plan.goal,
            "",
        ]

        for query, result in zip(plan.queries, results, strict=True):
            sections.extend(
                [
                    f"## {query.id}",
                    "",
                    f"Status: {result.status}",
                    "",
                    f"Executor: {result.executor}",
                    "",
                    "Query:",
                    "",
                    query.instruction or self._describe_query(query),
                    "",
                    "Evidence:",
                    "",
                    result.evidence or "(none)",
                    "",
                ]
            )
            if result.error:
                sections.extend(["Error:", "", result.error, ""])

        (run_dir / "evidence.md").write_text(
            "\n".join(sections),
            encoding="utf-8",
        )

    def _describe_query(self, query: InvestigationQuery) -> str:
        data = query.model_dump(mode="json", exclude_none=True)
        return json.dumps(data, ensure_ascii=False)
