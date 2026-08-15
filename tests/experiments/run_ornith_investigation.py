import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import yaml

from reposcout.models import InvestigationQuery
from reposcout.runner import QueryRunner


def load_cases(path: Path) -> list[dict[str, str]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload["cases"]


def execute_case(
    runner: QueryRunner,
    root: Path,
    case: dict[str, str],
) -> dict[str, str | float]:
    query = InvestigationQuery(
        id=case["id"],
        instruction=case["instruction"],
    )

    started = time.perf_counter()
    result = runner.execute(root, query)
    elapsed = time.perf_counter() - started

    return {
        "id": case["id"],
        "title": case["title"],
        "instruction": case["instruction"],
        "status": result.status,
        "executor": result.executor,
        "evidence": result.evidence,
        "error": result.error or "",
        "elapsed_seconds": round(elapsed, 3),
    }


def write_markdown(
    path: Path,
    results: list[dict[str, str]],
) -> None:
    lines = ["# Ornith Investigation Experiment", ""]

    for result in results:
        lines.extend(
            [
                f"## {result['id']} - {result['title']}",
                "",
                f"Status: {result['status']}",
                f"Elapsed: {result['elapsed_seconds']} sec",
                "",
                "### Instruction",
                "",
                result["instruction"],
                "",
                "### Evidence",
                "",
                "```text",
                result["evidence"],
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
                    result["error"],
                    "```",
                    "",
                ]
            )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("tests/experiments/cases.yaml"),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    cases = load_cases(args.cases)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path("tests/experiments/results") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    runner = QueryRunner()

    results = [execute_case(runner, root, case) for case in cases]

    json_path = output_dir / "results.json"
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown_path = output_dir / "results.md"
    write_markdown(markdown_path, results)

    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")

    failed = sum(result["status"] != "PASS" for result in results)

    print(f"Cases: {len(results)}")
    print(f"PASS: {len(results) - failed}")
    print(f"ERROR: {failed}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
