import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from reposcout.models import InvestigationPlan, InvestigationQuery, PackRequest, QueryTool
from reposcout.pack import EvidencePackBuilder
from reposcout.runner import InvestigationRunner, QueryRunner
from reposcout.scope import FileScopeMode, RepositoryFileScope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reposcout")
    subparsers = parser.add_subparsers(dest="command", required=True)

    query = subparsers.add_parser("query")
    query.add_argument("--root", type=Path, default=Path.cwd())
    query.add_argument("--id", default="Q1")
    query.add_argument("--instruction")
    query.add_argument("--tool", choices=[item.value for item in QueryTool])
    query.add_argument("--pattern")
    query.add_argument("--path", action="append", default=[])
    query.add_argument("--file")
    query.add_argument("--start-line", type=int)
    query.add_argument("--end-line", type=int)
    query.add_argument("--git-arg", action="append", default=[])

    investigate = subparsers.add_parser("investigate")
    investigate.add_argument("plan", type=Path)
    investigate.add_argument("--root", type=Path, default=Path.cwd())
    investigate.add_argument("--output", type=Path)

    skeleton = subparsers.add_parser("skeleton")
    skeleton.add_argument("--root", type=Path, default=Path.cwd())
    skeleton.add_argument(
        "--scope",
        choices=[item.value for item in FileScopeMode],
        default=FileScopeMode.TRACKED_ONLY.value,
    )

    pack = subparsers.add_parser("pack")
    pack.add_argument("request", type=Path)
    pack.add_argument("--root", type=Path, default=Path.cwd())

    return parser


def run_query(args: argparse.Namespace) -> int:
    query = InvestigationQuery(
        id=args.id,
        instruction=args.instruction,
        tool=QueryTool(args.tool) if args.tool else None,
        pattern=args.pattern,
        paths=args.path,
        file=args.file,
        start_line=args.start_line,
        end_line=args.end_line,
        git_args=args.git_arg,
    )

    started = time.perf_counter()
    result = QueryRunner().execute(args.root.resolve(), query)
    elapsed = time.perf_counter() - started

    print(result.model_dump_json(indent=2))
    print(f"Elapsed: {elapsed:.3f} sec")

    return 0 if result.status == "PASS" else 1


def _parse_request(path: Path, model: type[InvestigationPlan | PackRequest]) -> Any:
    """Load a YAML request file and validate it, or raise a plain ValueError.

    Malformed input is expected here (it is caller-authored, not developer
    error), so yaml.YAMLError / pydantic's ValidationError are normalized to
    ValueError -- one exception type every call site can catch at the CLI
    boundary instead of leaking a traceback.
    """
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return model.model_validate(payload)
    except (yaml.YAMLError, ValidationError) as error:
        raise ValueError(str(error)) from error


def run_investigate(args: argparse.Namespace) -> int:
    try:
        plan = _parse_request(args.plan, InvestigationPlan)
    except ValueError as error:
        print(json.dumps({"error": str(error)}, indent=2))
        return 1

    run_dir = args.output or _default_run_dir(args.root.resolve())

    started = time.perf_counter()
    results = InvestigationRunner().execute(
        root=args.root.resolve(),
        plan=plan,
        run_dir=run_dir,
    )
    elapsed = time.perf_counter() - started

    passed = sum(item.status == "PASS" for item in results)
    failed = len(results) - passed

    print(f"Evidence Pack: {run_dir / 'evidence.md'}")
    print(f"Queries: {len(results)}")
    print(f"PASS: {passed}")
    print(f"ERROR: {failed}")
    print(f"Elapsed: {elapsed:.3f} sec")

    return 0 if failed == 0 else 1


def run_skeleton(args: argparse.Namespace) -> int:
    scope = RepositoryFileScope(FileScopeMode(args.scope))
    try:
        files = scope.list_files(args.root.resolve())
    except RuntimeError as error:
        print(json.dumps({"error": str(error)}, indent=2))
        return 1

    for path in files:
        print(path)
    return 0


def run_pack(args: argparse.Namespace) -> int:
    try:
        request = _parse_request(args.request, PackRequest)
        pack = EvidencePackBuilder().build(args.root.resolve(), request.ranges)
    except ValueError as error:
        print(json.dumps({"error": str(error)}, indent=2))
        return 1

    print(pack.model_dump_json(indent=2))
    return 0


def _default_run_dir(root: Path) -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    return root / ".reposcout" / "runs" / run_id


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "query":
        return run_query(args)

    if args.command == "investigate":
        return run_investigate(args)

    if args.command == "skeleton":
        return run_skeleton(args)

    if args.command == "pack":
        return run_pack(args)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
