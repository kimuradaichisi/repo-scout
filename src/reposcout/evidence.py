import json
from pathlib import Path

import yaml

from reposcout.models import (
    EvidenceContract,
    EvidencePack,
    EvidenceResult,
    InvestigationPlan,
    InvestigationQuery,
    QueryEvidence,
    SourceLocation,
    UnknownEvidence,
)


class EvidenceWriter:
    def build_contract(
        self,
        plan: InvestigationPlan,
        results: list[EvidenceResult],
        pack: EvidencePack | None = None,
    ) -> EvidenceContract:
        query_evidence = self._build_query_evidence(plan, results)
        locations = self._collect_source_locations(query_evidence, pack)
        return EvidenceContract(
            goal=plan.goal,
            query_evidence=query_evidence,
            source_locations=self._deduplicate_locations(locations),
            unknown=self._build_unknown(results),
        )

    def _build_query_evidence(
        self, plan: InvestigationPlan, results: list[EvidenceResult]
    ) -> list[QueryEvidence]:
        return [
            QueryEvidence(
                query_id=result.query_id,
                question=query.instruction or self._describe_query(query),
                executor=result.executor,
                status=result.status,
                evidence=result.evidence,
                source_locations=list(result.source_locations),
            )
            for query, result in zip(plan.queries, results, strict=False)
        ]

    def _build_unknown(self, results: list[EvidenceResult]) -> list[UnknownEvidence]:
        return [
            UnknownEvidence(
                query_id=result.query_id,
                status=result.status,
                reason=result.error or f"status={result.status}",
            )
            for result in results
            if result.status in {"ERROR", "UNRESOLVED"}
        ]

    def _collect_source_locations(
        self, query_evidence: list[QueryEvidence], pack: EvidencePack | None
    ) -> list[SourceLocation]:
        locations = [location for item in query_evidence for location in item.source_locations]
        if pack:
            locations.extend(
                SourceLocation(
                    path=source.path,
                    start_line=source.start_line,
                    end_line=source.end_line,
                    content_hash=source.sha256,
                )
                for source in pack.sources
            )
        return locations

    def write_contract(self, run_dir: Path, contract: EvidenceContract) -> None:
        (run_dir / "evidence-contract.json").write_text(
            json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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

    def _deduplicate_locations(self, locations: list[SourceLocation]) -> list[SourceLocation]:
        unique: list[SourceLocation] = []
        seen: set[tuple[str, int, int, str | None]] = set()
        for location in locations:
            key = (location.path, location.start_line, location.end_line, location.content_hash)
            if key not in seen:
                seen.add(key)
                unique.append(location)
        return unique
