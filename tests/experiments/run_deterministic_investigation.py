import json
import time
from datetime import datetime
from pathlib import Path

from reposcout.models import InvestigationQuery, QueryTool
from reposcout.runner import QueryRunner


def execute_case(
    runner: QueryRunner,
    root: Path,
    case: dict[str, str],
) -> dict[str, str | float]:
    query = InvestigationQuery(
        id=case["id"],
        tool=QueryTool.RG,
        pattern=case["pattern"],
        paths=["src/reposcout"],
    )

    started = time.perf_counter()
    result = runner.execute(root, query)
    elapsed = time.perf_counter() - started

    return {
        "id": case["id"],
        "title": case["title"],
        "pattern": case["pattern"],
        "status": result.status,
        "executor": result.executor,
        "evidence": result.evidence,
        "error": result.error or "",
        "elapsed_seconds": round(elapsed, 3),
    }


def write_markdown(
    path: Path,
    results: list[dict[str, str | float]],
) -> None:
    lines = ["# Deterministic Investigation Experiment", ""]

    for result in results:
        lines.extend(
            [
                f"## {result['id']} - {result['title']}",
                "",
                f"Status: {result['status']}",
                f"Executor: {result['executor']}",
                f"Elapsed: {result['elapsed_seconds']} sec",
                "",
                "### Pattern",
                "",
                str(result["pattern"]),
                "",
                "### Evidence",
                "",
                "```text",
                str(result["evidence"]),
                "```",
                "",
            ]
        )

        if result["error"]:
            lines.extend(
                [
                    "### Error",
                    "",
                    "```text",
                    str(result["error"]),
                    "```",
                    "",
                ]
            )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    root = Path.cwd().resolve()

    cases = [
        {
            "id": "Q1",
            "title": "definition lookup",
            "pattern": "InvestigationRunner",
        },
        {
            "id": "Q2",
            "title": "reference lookup",
            "pattern": "EvidenceWriter",
        },
        {
            "id": "Q3",
            "title": "behavioral lookup",
            "pattern": "InvestigationPlan",
        },
    ]

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path("tests/experiments/results") / f"{timestamp}-deterministic"
    output_dir.mkdir(parents=True, exist_ok=True)

    runner = QueryRunner()

    started = time.perf_counter()

    results = [
        execute_case(
            runner=runner,
            root=root,
            case=case,
        )
        for case in cases
    ]

    total_elapsed = time.perf_counter() - started

    json_path = output_dir / "results.json"
    json_path.write_text(
        json.dumps(
            {
                "total_elapsed_seconds": round(total_elapsed, 3),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    markdown_path = output_dir / "results.md"
    write_markdown(markdown_path, results)

    failed = sum(result["status"] != "PASS" for result in results)

    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    print(f"Cases: {len(results)}")
    print(f"PASS: {len(results) - failed}")
    print(f"ERROR: {failed}")
    print(f"Total: {total_elapsed:.3f} sec")

    for result in results:
        print(f"  {result['id']}: {result['elapsed_seconds']} sec [{result['status']}]")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
