"""Compare Claude Code alone (A) against Claude Code + RepoScout (B).

Both patterns investigate the same question against the same frozen snapshot of
this repository, so the only difference is who executes rg/read/git_log.
"""

import argparse
import json
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from claude_metrics import ClaudeRun, run_claude
from prompts import (
    ANALYSIS_PROMPT_TEMPLATE,
    ANALYSIS_PROMPT_TEMPLATE_B2,
    BASELINE_PROMPT,
    EXPLORER_PLAN_PROMPT_TEMPLATE,
    EXPLORER_SYNTHESIS_PROMPT_TEMPLATE,
    MAIN_BRIEF_PROMPT,
    MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE,
    MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1,
    PLAN_PROMPT,
    PLAN_PROMPT_WITH_SKELETON,
    REPOSITORY_FILES_PLACEHOLDER,
)

# B3 fixes the model per role; --model only applies to b1/b2.
MAIN_MODEL = "claude-opus-5"
EXPLORER_MODEL = "claude-sonnet-5"

# Tools each pattern is allowed to use. Read-only by construction.
INVESTIGATION_TOOLS = (
    "Read,Grep,Glob,Bash(rg:*),Bash(git log:*),Bash(git show:*),"
    "Bash(ls:*),Bash(find:*),Bash(cat:*),Bash(wc:*),Bash(head:*),Bash(tail:*)"
)
NO_TOOLS_DISALLOWED = (
    "Read,Grep,Glob,Bash,Task,Write,Edit,NotebookEdit,WebFetch,WebSearch,TodoWrite"
)
BLOCKED_WRITE_TOOLS = "Write,Edit,NotebookEdit,Task,WebFetch,WebSearch"

# Files/symbols a correct answer must mention. Verified against the snapshot.
EXPECTED_FILES = [
    "runner.py",
    "cli.py",
    "evidence.py",
    "models.py",
]
EXPECTED_SYMBOLS = [
    "QueryRunner",
    "EvidenceWriter",
    "InvestigationPlan",
    "EvidenceResult",
]
EXPECTED_EXTENDED = [
    "executors",
    "ornith",
]
TEST_GAP_PATTERN = re.compile(
    r"(テスト|test).{0,40}(存在しない|無い|ない|不在|未整備|不足|見つから|なし)"
)

SNAPSHOT_INCLUDES = [
    "src",
    "examples",
    "docs",
    "README.md",
    "pyproject.toml",
    "Makefile",
    "uv.lock",
]


def build_snapshot(source: Path, destination: Path) -> Path:
    """Copy the code under investigation into a clean, git-initialised tree.

    tests/experiments is intentionally excluded: this harness itself mentions
    the target symbol and would show up as grep noise for pattern A.

    The destination must live outside the source repository. When it sat under
    tests/experiments/results, Claude walked up the absolute cwd, found the real
    repository and grepped the harness itself.
    """
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError("snapshot must live outside the repository under investigation")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    for name in SNAPSHOT_INCLUDES:
        origin = source / name
        if not origin.exists():
            continue
        if origin.is_dir():
            shutil.copytree(
                origin,
                destination / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        else:
            shutil.copy2(origin, destination / name)

    unit_tests = source / "tests" / "unit"
    if unit_tests.exists():
        shutil.copytree(
            unit_tests,
            destination / "tests" / "unit",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    _strip_experiment_targets(destination / "Makefile")

    subprocess.run(["git", "init", "-q"], cwd=destination, check=True)
    subprocess.run(["git", "add", "-A"], cwd=destination, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=experiment",
            "-c",
            "user.email=experiment@local",
            "commit",
            "-qm",
            "snapshot under investigation",
        ],
        cwd=destination,
        check=True,
    )
    return destination


def _strip_experiment_targets(makefile: Path) -> None:
    """Drop make targets pointing at tests/experiments, which the snapshot omits.

    Left in place, both patterns spend turns reporting that the harness scripts
    are missing — an artefact of the snapshot, not a property of the code.
    """
    if not makefile.exists():
        return

    kept: list[str] = []
    skipping = False
    for line in makefile.read_text(encoding="utf-8").splitlines():
        if re.match(r"^experiment[\w-]*:", line):
            skipping = True
            continue
        if skipping:
            if line.startswith("\t") or not line.strip():
                continue
            skipping = False
        kept.append(line)

    makefile.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")


def score_answer(text: str) -> dict[str, Any]:
    lowered = text.lower()

    found_files = [item for item in EXPECTED_FILES if item.lower() in lowered]
    found_symbols = [item for item in EXPECTED_SYMBOLS if item.lower() in lowered]
    found_extended = [item for item in EXPECTED_EXTENDED if item.lower() in lowered]

    expected_total = len(EXPECTED_FILES) + len(EXPECTED_SYMBOLS) + len(EXPECTED_EXTENDED)
    found_total = len(found_files) + len(found_symbols) + len(found_extended)

    return {
        "found_files": found_files,
        "missing_files": [item for item in EXPECTED_FILES if item not in found_files],
        "found_symbols": found_symbols,
        "missing_symbols": [item for item in EXPECTED_SYMBOLS if item not in found_symbols],
        "found_extended": found_extended,
        "coverage": round(found_total / expected_total, 3),
        "mentions_test_gap": bool(TEST_GAP_PATTERN.search(text)),
        "answer_chars": len(text),
    }


def list_repository_files(snapshot: Path) -> str:
    """Deterministic Repository Files list for the B2 skeleton: tracked paths only.

    No new analysis code — this is exactly `git ls-files src tests/unit` against
    the snapshot, so every path handed to the plan prompt is known to exist.
    """
    completed = subprocess.run(
        ["git", "ls-files", "src", "tests/unit"],
        cwd=snapshot,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def count_repo_leaks(transcript: Path, repo_root: Path) -> int:
    """Count references to the real repository inside a run's transcript.

    The snapshot lives outside the repository, so any mention means Claude
    escaped the fixture and the run's numbers are contaminated.
    """
    if not transcript.exists():
        return 0
    text = transcript.read_text(encoding="utf-8", errors="replace")
    return text.count(str(repo_root))


def extract_yaml(text: str) -> str:
    fenced = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    if fenced:
        return max(fenced, key=len).strip()
    return text.strip()


def run_pattern_a(
    snapshot: Path,
    run_dir: Path,
    repo_root: Path,
    model: str,
    iteration: int,
) -> dict[str, Any]:
    transcript = run_dir / f"A{iteration}-baseline.jsonl"
    run = run_claude(
        BASELINE_PROMPT,
        label=f"A-baseline-{iteration}",
        root=snapshot,
        transcript_path=transcript,
        model=model,
        allowed_tools=INVESTIGATION_TOOLS,
        disallowed_tools=BLOCKED_WRITE_TOOLS,
    )
    (run_dir / f"A{iteration}-answer.md").write_text(run.final_text, encoding="utf-8")

    payload = run.to_dict()
    payload["quality"] = score_answer(run.final_text)
    payload["repo_leaks"] = count_repo_leaks(transcript, repo_root)
    payload["totals"] = {
        "claude_total_input_tokens": run.total_input_tokens,
        "claude_output_tokens": run.output_tokens,
        "claude_total_tokens": run.total_tokens,
        "claude_cost_usd": round(run.cost_usd, 6),
        "claude_grep_calls": run.grep_calls,
        "claude_read_calls": run.read_calls,
        "claude_bash_calls": run.bash_calls,
        "claude_file_count": run.file_count,
        "wall_seconds": round(run.wall_seconds, 3),
    }
    return payload


def run_reposcout(
    snapshot: Path,
    plan_path: Path,
    output_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        [
            "uv",
            "run",
            "reposcout",
            "investigate",
            str(plan_path),
            "--root",
            str(snapshot),
            "--output",
            str(output_dir),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - started

    evidence_path = output_dir / "evidence.md"
    evidence = evidence_path.read_text(encoding="utf-8") if evidence_path.exists() else ""

    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip()[:2000],
        "elapsed_seconds": round(elapsed, 3),
        "evidence_path": str(evidence_path),
        "evidence_chars": len(evidence),
        "evidence": evidence,
        **inspect_query_results(output_dir),
    }


def inspect_query_results(output_dir: Path) -> dict[str, Any]:
    """Break query outcomes down by executor.

    A query that returns PASS with empty evidence is a miss in practice — it
    tells Claude nothing — so it is tracked separately from a hard ERROR.
    """
    failed_by_executor: dict[str, int] = {}
    failed = 0
    empty = 0
    effective = 0
    total = 0

    for path in sorted(output_dir.glob("Q*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        total += 1
        executor = str(result.get("executor", "unknown"))

        if result.get("status") != "PASS":
            failed += 1
            failed_by_executor[executor] = failed_by_executor.get(executor, 0) + 1
        elif not str(result.get("evidence", "")).strip():
            empty += 1
        else:
            effective += 1

    return {
        "query_count": total,
        "failed_query_count": failed,
        "empty_evidence_count": empty,
        "effective_query_count": effective,
        "failed_read_count": failed_by_executor.get("file_read", 0),
        "failed_search_count": failed_by_executor.get("ripgrep", 0),
        "failed_git_log_count": failed_by_executor.get("git_log", 0),
        "failed_by_executor": failed_by_executor,
    }


def run_pattern_b(
    snapshot: Path,
    run_dir: Path,
    repo_root: Path,
    model: str,
    iteration: int,
) -> dict[str, Any]:
    plan_run = run_claude(
        PLAN_PROMPT,
        label=f"B-plan-{iteration}",
        root=snapshot,
        transcript_path=run_dir / f"B{iteration}-plan.jsonl",
        model=model,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )

    plan_text = extract_yaml(plan_run.final_text)
    plan_path = run_dir / f"B{iteration}-plan.yaml"
    plan_path.write_text(plan_text, encoding="utf-8")

    plan_error = ""
    query_count = 0
    tool_breakdown: dict[str, int] = {}
    try:
        parsed = yaml.safe_load(plan_text)
        queries = parsed.get("queries", []) if isinstance(parsed, dict) else []
        query_count = len(queries)
        for query in queries:
            tool = str(query.get("tool", "ornith(unspecified)"))
            tool_breakdown[tool] = tool_breakdown.get(tool, 0) + 1
    except yaml.YAMLError as exc:
        plan_error = str(exc)

    scout = run_reposcout(
        snapshot=snapshot,
        plan_path=plan_path,
        output_dir=run_dir / f"B{iteration}-scout",
        repo_root=repo_root,
    )

    analysis_transcript = run_dir / f"B{iteration}-analysis.jsonl"
    analysis_run = run_claude(
        ANALYSIS_PROMPT_TEMPLATE.format(evidence=scout["evidence"]),
        label=f"B-analysis-{iteration}",
        root=snapshot,
        transcript_path=analysis_transcript,
        model=model,
        allowed_tools=INVESTIGATION_TOOLS,
        disallowed_tools=BLOCKED_WRITE_TOOLS,
    )
    (run_dir / f"B{iteration}-answer.md").write_text(analysis_run.final_text, encoding="utf-8")

    return _summarise_pattern_b(
        plan_run=plan_run,
        analysis_run=analysis_run,
        scout=scout,
        plan_error=plan_error,
        query_count=query_count,
        tool_breakdown=tool_breakdown,
        plan_path=plan_path,
        repo_leaks=count_repo_leaks(analysis_transcript, repo_root),
    )


def run_pattern_b2(
    snapshot: Path,
    run_dir: Path,
    repo_root: Path,
    model: str,
    iteration: int,
) -> dict[str, Any]:
    """B2 = B1 + a Repository Files skeleton injected before plan generation."""
    repository_files = list_repository_files(snapshot)

    plan_run = run_claude(
        PLAN_PROMPT_WITH_SKELETON.format(repository_files=repository_files),
        label=f"B2-plan-{iteration}",
        root=snapshot,
        transcript_path=run_dir / f"B2-{iteration}-plan.jsonl",
        model=model,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )

    plan_text = extract_yaml(plan_run.final_text)
    plan_path = run_dir / f"B2-{iteration}-plan.yaml"
    plan_path.write_text(plan_text, encoding="utf-8")

    plan_error = ""
    query_count = 0
    tool_breakdown: dict[str, int] = {}
    try:
        parsed = yaml.safe_load(plan_text)
        queries = parsed.get("queries", []) if isinstance(parsed, dict) else []
        query_count = len(queries)
        for query in queries:
            tool = str(query.get("tool", "ornith(unspecified)"))
            tool_breakdown[tool] = tool_breakdown.get(tool, 0) + 1
    except yaml.YAMLError as exc:
        plan_error = str(exc)

    scout = run_reposcout(
        snapshot=snapshot,
        plan_path=plan_path,
        output_dir=run_dir / f"B2-{iteration}-scout",
        repo_root=repo_root,
    )

    analysis_transcript = run_dir / f"B2-{iteration}-analysis.jsonl"
    analysis_run = run_claude(
        ANALYSIS_PROMPT_TEMPLATE_B2.format(evidence=scout["evidence"]),
        label=f"B2-analysis-{iteration}",
        root=snapshot,
        transcript_path=analysis_transcript,
        model=model,
        allowed_tools=INVESTIGATION_TOOLS,
        disallowed_tools=BLOCKED_WRITE_TOOLS,
    )
    (run_dir / f"B2-{iteration}-answer.md").write_text(analysis_run.final_text, encoding="utf-8")

    return _summarise_pattern_b(
        plan_run=plan_run,
        analysis_run=analysis_run,
        scout=scout,
        plan_error=plan_error,
        query_count=query_count,
        tool_breakdown=tool_breakdown,
        plan_path=plan_path,
        repo_leaks=count_repo_leaks(analysis_transcript, repo_root),
        extra_totals={
            "repository_files_count": len(repository_files.splitlines()) if repository_files else 0,
            "repository_files_chars": len(repository_files),
            "plan_input_tokens": plan_run.total_input_tokens,
            "analysis_input_tokens": analysis_run.total_input_tokens,
        },
    )


def _summarise_pattern_b(
    plan_run: ClaudeRun,
    analysis_run: ClaudeRun,
    scout: dict[str, Any],
    plan_error: str,
    query_count: int,
    tool_breakdown: dict[str, int],
    plan_path: Path,
    repo_leaks: int,
    extra_totals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scout_summary = {key: value for key, value in scout.items() if key != "evidence"}

    return {
        "plan": plan_run.to_dict(),
        "analysis": analysis_run.to_dict(),
        "reposcout": scout_summary,
        "repo_leaks": repo_leaks,
        "plan_path": str(plan_path),
        "plan_error": plan_error,
        "plan_query_count": query_count,
        "plan_tool_breakdown": tool_breakdown,
        "quality": score_answer(analysis_run.final_text),
        "totals": {
            **(extra_totals or {}),
            "claude_total_input_tokens": (
                plan_run.total_input_tokens + analysis_run.total_input_tokens
            ),
            "claude_output_tokens": plan_run.output_tokens + analysis_run.output_tokens,
            "claude_total_tokens": plan_run.total_tokens + analysis_run.total_tokens,
            "claude_cost_usd": round(plan_run.cost_usd + analysis_run.cost_usd, 6),
            "claude_grep_calls": plan_run.grep_calls + analysis_run.grep_calls,
            "claude_read_calls": plan_run.read_calls + analysis_run.read_calls,
            "claude_bash_calls": plan_run.bash_calls + analysis_run.bash_calls,
            "claude_file_count": len(set(plan_run.files_touched) | set(analysis_run.files_touched)),
            "reposcout_query_count": query_count,
            "wall_seconds": round(
                plan_run.wall_seconds + scout["elapsed_seconds"] + analysis_run.wall_seconds,
                3,
            ),
            # Everything below is B-only: how badly the plan missed, and how
            # much Claude had to re-investigate on its own to recover.
            "failed_query_count": scout.get("failed_query_count", 0),
            "empty_evidence_count": scout.get("empty_evidence_count", 0),
            "effective_query_count": scout.get("effective_query_count", 0),
            "failed_read_count": scout.get("failed_read_count", 0),
            "failed_search_count": scout.get("failed_search_count", 0),
            "fallback_read_calls": analysis_run.read_calls,
            "fallback_search_calls": analysis_run.grep_calls,
            "evidence_chars": scout.get("evidence_chars", 0),
        },
    }


def run_pattern_b3(
    snapshot: Path,
    run_dir: Path,
    repo_root: Path,
    iteration: int,
) -> dict[str, Any]:
    """B3 = Main(Opus) writes a Brief -> Explorer(Sonnet) runs B2's plan -> RepoScout
    -> evidence flow -> Explorer returns an Evidence Pack -> Main(Opus) analyses it.

    Main never sees a transcript: only the Brief text going out and the Evidence
    Pack text coming back. RepoScout itself (run_reposcout) is identical to B1/B2.
    """
    repository_files = list_repository_files(snapshot)

    brief_run = run_claude(
        MAIN_BRIEF_PROMPT,
        label=f"B3-main-brief-{iteration}",
        root=snapshot,
        transcript_path=run_dir / f"B3-{iteration}-main-brief.jsonl",
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    brief_text = brief_run.final_text.strip()
    if REPOSITORY_FILES_PLACEHOLDER in brief_text:
        handoff = brief_text.replace(REPOSITORY_FILES_PLACEHOLDER, repository_files)
    else:
        # Main didn't emit the placeholder as instructed; append the real
        # REPOSITORY FILES section rather than silently handing Explorer
        # a Brief with no file list to constrain it.
        handoff = f"{brief_text}\n\nREPOSITORY FILES\n{repository_files}"

    explorer_plan_run = run_claude(
        EXPLORER_PLAN_PROMPT_TEMPLATE.format(handoff=handoff),
        label=f"B3-explorer-plan-{iteration}",
        root=snapshot,
        transcript_path=run_dir / f"B3-{iteration}-explorer-plan.jsonl",
        model=EXPLORER_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )

    plan_text = extract_yaml(explorer_plan_run.final_text)
    plan_path = run_dir / f"B3-{iteration}-plan.yaml"
    plan_path.write_text(plan_text, encoding="utf-8")

    plan_error = ""
    query_count = 0
    tool_breakdown: dict[str, int] = {}
    try:
        parsed = yaml.safe_load(plan_text)
        queries = parsed.get("queries", []) if isinstance(parsed, dict) else []
        query_count = len(queries)
        for query in queries:
            tool = str(query.get("tool", "ornith(unspecified)"))
            tool_breakdown[tool] = tool_breakdown.get(tool, 0) + 1
    except yaml.YAMLError as exc:
        plan_error = str(exc)

    scout = run_reposcout(
        snapshot=snapshot,
        plan_path=plan_path,
        output_dir=run_dir / f"B3-{iteration}-scout",
        repo_root=repo_root,
    )

    explorer_synthesis_transcript = run_dir / f"B3-{iteration}-explorer-synthesis.jsonl"
    explorer_synthesis_run = run_claude(
        EXPLORER_SYNTHESIS_PROMPT_TEMPLATE.format(handoff=handoff, evidence=scout["evidence"]),
        label=f"B3-explorer-synthesis-{iteration}",
        root=snapshot,
        transcript_path=explorer_synthesis_transcript,
        model=EXPLORER_MODEL,
        allowed_tools=INVESTIGATION_TOOLS,
        disallowed_tools=BLOCKED_WRITE_TOOLS,
    )
    evidence_pack = explorer_synthesis_run.final_text.strip()
    (run_dir / f"B3-{iteration}-evidence-pack.md").write_text(evidence_pack, encoding="utf-8")

    main_final_transcript = run_dir / f"B3-{iteration}-main-final.jsonl"
    main_final_run = run_claude(
        MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE.format(evidence_pack=evidence_pack),
        label=f"B3-main-final-{iteration}",
        root=snapshot,
        transcript_path=main_final_transcript,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (run_dir / f"B3-{iteration}-answer.md").write_text(main_final_run.final_text, encoding="utf-8")

    repo_leaks = (
        count_repo_leaks(run_dir / f"B3-{iteration}-explorer-plan.jsonl", repo_root)
        + count_repo_leaks(explorer_synthesis_transcript, repo_root)
        + count_repo_leaks(main_final_transcript, repo_root)
    )

    scout_summary = {key: value for key, value in scout.items() if key != "evidence"}
    main_opus_input_tokens = brief_run.total_input_tokens + main_final_run.total_input_tokens
    main_opus_output_tokens = brief_run.output_tokens + main_final_run.output_tokens
    explorer_sonnet_input_tokens = (
        explorer_plan_run.total_input_tokens + explorer_synthesis_run.total_input_tokens
    )
    explorer_sonnet_output_tokens = (
        explorer_plan_run.output_tokens + explorer_synthesis_run.output_tokens
    )

    return {
        "main_brief": brief_run.to_dict(),
        "explorer_plan": explorer_plan_run.to_dict(),
        "explorer_synthesis": explorer_synthesis_run.to_dict(),
        "main_final": main_final_run.to_dict(),
        "reposcout": scout_summary,
        "repo_leaks": repo_leaks,
        "handoff": handoff,
        "evidence_pack": evidence_pack,
        "plan_path": str(plan_path),
        "plan_error": plan_error,
        "plan_query_count": query_count,
        "plan_tool_breakdown": tool_breakdown,
        "quality": score_answer(main_final_run.final_text),
        "totals": {
            "main_opus_input_tokens": main_opus_input_tokens,
            "main_opus_output_tokens": main_opus_output_tokens,
            "explorer_sonnet_input_tokens": explorer_sonnet_input_tokens,
            "explorer_sonnet_output_tokens": explorer_sonnet_output_tokens,
            "handoff_brief_chars": len(handoff),
            "evidence_pack_chars": len(evidence_pack),
            "repository_files_count": (
                len(repository_files.splitlines()) if repository_files else 0
            ),
            "repository_files_chars": len(repository_files),
            "explorer_tool_calls": (
                explorer_synthesis_run.grep_calls + explorer_synthesis_run.read_calls
            ),
            "explorer_fallback_read_calls": explorer_synthesis_run.read_calls,
            "explorer_fallback_search_calls": explorer_synthesis_run.grep_calls,
            "reposcout_query_count": query_count,
            "effective_query_count": scout.get("effective_query_count", 0),
            "failed_query_count": scout.get("failed_query_count", 0),
            "empty_evidence_count": scout.get("empty_evidence_count", 0),
            "failed_read_count": scout.get("failed_read_count", 0),
            "failed_search_count": scout.get("failed_search_count", 0),
            "evidence_chars": scout.get("evidence_chars", 0),
            "total_input_tokens": main_opus_input_tokens + explorer_sonnet_input_tokens,
            "total_output_tokens": main_opus_output_tokens + explorer_sonnet_output_tokens,
            "total_cost_usd": round(
                brief_run.cost_usd
                + explorer_plan_run.cost_usd
                + explorer_synthesis_run.cost_usd
                + main_final_run.cost_usd,
                6,
            ),
            "wall_seconds": round(
                brief_run.wall_seconds
                + explorer_plan_run.wall_seconds
                + scout["elapsed_seconds"]
                + explorer_synthesis_run.wall_seconds
                + main_final_run.wall_seconds,
                3,
            ),
        },
    }


def run_pattern_b3_1(
    snapshot: Path,
    run_dir: Path,
    repo_root: Path,
    iteration: int,
) -> dict[str, Any]:
    """B3.1 = B3 minus the Explorer synthesis call.

    Main(Opus) writes a Brief -> Explorer(Sonnet) runs B2's plan -> RepoScout ->
    Main(Opus) analyses RepoScout's raw evidence.md directly, no intermediate
    Sonnet summarisation step. Tests whether that step was buying anything.
    """
    repository_files = list_repository_files(snapshot)

    brief_run = run_claude(
        MAIN_BRIEF_PROMPT,
        label=f"B3.1-main-brief-{iteration}",
        root=snapshot,
        transcript_path=run_dir / f"B3.1-{iteration}-main-brief.jsonl",
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    brief_text = brief_run.final_text.strip()
    if REPOSITORY_FILES_PLACEHOLDER in brief_text:
        handoff = brief_text.replace(REPOSITORY_FILES_PLACEHOLDER, repository_files)
    else:
        handoff = f"{brief_text}\n\nREPOSITORY FILES\n{repository_files}"

    explorer_plan_transcript = run_dir / f"B3.1-{iteration}-explorer-plan.jsonl"
    explorer_plan_run = run_claude(
        EXPLORER_PLAN_PROMPT_TEMPLATE.format(handoff=handoff),
        label=f"B3.1-explorer-plan-{iteration}",
        root=snapshot,
        transcript_path=explorer_plan_transcript,
        model=EXPLORER_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )

    plan_text = extract_yaml(explorer_plan_run.final_text)
    plan_path = run_dir / f"B3.1-{iteration}-plan.yaml"
    plan_path.write_text(plan_text, encoding="utf-8")

    plan_error = ""
    query_count = 0
    tool_breakdown: dict[str, int] = {}
    try:
        parsed = yaml.safe_load(plan_text)
        queries = parsed.get("queries", []) if isinstance(parsed, dict) else []
        query_count = len(queries)
        for query in queries:
            tool = str(query.get("tool", "ornith(unspecified)"))
            tool_breakdown[tool] = tool_breakdown.get(tool, 0) + 1
    except yaml.YAMLError as exc:
        plan_error = str(exc)

    scout = run_reposcout(
        snapshot=snapshot,
        plan_path=plan_path,
        output_dir=run_dir / f"B3.1-{iteration}-scout",
        repo_root=repo_root,
    )

    main_final_transcript = run_dir / f"B3.1-{iteration}-main-final.jsonl"
    main_final_prompt = MAIN_FINAL_ANALYSIS_PROMPT_TEMPLATE_B3_1.format(
        handoff=handoff, evidence=scout["evidence"]
    )
    main_final_run = run_claude(
        main_final_prompt,
        label=f"B3.1-main-final-{iteration}",
        root=snapshot,
        transcript_path=main_final_transcript,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    (run_dir / f"B3.1-{iteration}-answer.md").write_text(
        main_final_run.final_text, encoding="utf-8"
    )

    repo_leaks = count_repo_leaks(explorer_plan_transcript, repo_root) + count_repo_leaks(
        main_final_transcript, repo_root
    )

    scout_summary = {key: value for key, value in scout.items() if key != "evidence"}
    main_opus_input_tokens = brief_run.total_input_tokens + main_final_run.total_input_tokens
    main_opus_output_tokens = brief_run.output_tokens + main_final_run.output_tokens
    explorer_sonnet_input_tokens = explorer_plan_run.total_input_tokens
    explorer_sonnet_output_tokens = explorer_plan_run.output_tokens

    return {
        "main_brief": brief_run.to_dict(),
        "explorer_plan": explorer_plan_run.to_dict(),
        "main_final": main_final_run.to_dict(),
        "reposcout": scout_summary,
        "repo_leaks": repo_leaks,
        "handoff": handoff,
        "plan_path": str(plan_path),
        "plan_error": plan_error,
        "plan_query_count": query_count,
        "plan_tool_breakdown": tool_breakdown,
        "quality": score_answer(main_final_run.final_text),
        "totals": {
            "main_opus_input_tokens": main_opus_input_tokens,
            "main_opus_output_tokens": main_opus_output_tokens,
            "explorer_sonnet_input_tokens": explorer_sonnet_input_tokens,
            "explorer_sonnet_output_tokens": explorer_sonnet_output_tokens,
            "handoff_brief_chars": len(handoff),
            "evidence_pack_chars": 0,  # no synthesis stage in B3.1
            "repository_files_count": (
                len(repository_files.splitlines()) if repository_files else 0
            ),
            "repository_files_chars": len(repository_files),
            # No Explorer synthesis stage exists in B3.1, so there is no tool
            # access at all between RepoScout and Main — these are always 0,
            # kept for schema parity with B3 rather than as a live signal.
            "explorer_tool_calls": 0,
            "explorer_fallback_read_calls": 0,
            "explorer_fallback_search_calls": 0,
            "reposcout_query_count": query_count,
            "effective_query_count": scout.get("effective_query_count", 0),
            "failed_query_count": scout.get("failed_query_count", 0),
            "empty_evidence_count": scout.get("empty_evidence_count", 0),
            "failed_read_count": scout.get("failed_read_count", 0),
            "failed_search_count": scout.get("failed_search_count", 0),
            "evidence_chars": scout.get("evidence_chars", 0),
            "total_input_tokens": main_opus_input_tokens + explorer_sonnet_input_tokens,
            "total_output_tokens": main_opus_output_tokens + explorer_sonnet_output_tokens,
            "total_cost_usd": round(
                brief_run.cost_usd + explorer_plan_run.cost_usd + main_final_run.cost_usd,
                6,
            ),
            "wall_seconds": round(
                brief_run.wall_seconds
                + explorer_plan_run.wall_seconds
                + scout["elapsed_seconds"]
                + main_final_run.wall_seconds,
                3,
            ),
        },
    }


def compare(a_totals: dict[str, Any], b_totals: dict[str, Any]) -> dict[str, Any]:
    def reduction(key: str) -> float | None:
        base = _value(a_totals.get(key))
        if not base:
            return None
        return round((base - _value(b_totals.get(key))) / base * 100, 1)

    return {
        "input_token_reduction_pct": reduction("claude_total_input_tokens"),
        "output_token_reduction_pct": reduction("claude_output_tokens"),
        "total_token_reduction_pct": reduction("claude_total_tokens"),
        "cost_reduction_pct": reduction("claude_cost_usd"),
        "read_call_reduction_pct": reduction("claude_read_calls"),
        "search_call_reduction_pct": reduction("claude_grep_calls"),
        "wall_seconds_reduction_pct": reduction("wall_seconds"),
    }


def _value(item: Any) -> float:
    """Read a metric that is either a raw number or a describe() block."""
    if isinstance(item, dict):
        return float(item.get("mean", 0.0))
    return float(item or 0)


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def describe(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "stdev": 0.0}

    return {
        "mean": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "stdev": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
    }


SHARED_KEYS = [
    "claude_total_input_tokens",
    "claude_output_tokens",
    "claude_total_tokens",
    "claude_cost_usd",
    "claude_grep_calls",
    "claude_read_calls",
    "claude_bash_calls",
    "claude_file_count",
    "wall_seconds",
]
B_ONLY_KEYS = [
    "reposcout_query_count",
    "effective_query_count",
    "failed_query_count",
    "empty_evidence_count",
    "failed_read_count",
    "failed_search_count",
    "fallback_read_calls",
    "fallback_search_calls",
    "evidence_chars",
]
# B2 only (Repository Files skeleton): present as 0 for B1 iterations.
B2_ONLY_KEYS = [
    "repository_files_count",
    "repository_files_chars",
    "plan_input_tokens",
    "analysis_input_tokens",
]


def aggregate(iterations: list[dict[str, Any]], variant: str = "b1") -> dict[str, Any]:
    summary: dict[str, Any] = {"iterations": len(iterations)}

    for pattern in ("a", "b"):
        totals = [item[pattern]["totals"] for item in iterations]
        b_keys = B_ONLY_KEYS + (B2_ONLY_KEYS if variant == "b2" else [])
        keys = SHARED_KEYS + (b_keys if pattern == "b" else [])
        summary[pattern] = {
            key: describe([float(total.get(key, 0)) for total in totals]) for key in keys
        }
        summary[pattern]["coverage"] = describe(
            [float(item[pattern]["quality"]["coverage"]) for item in iterations]
        )

    summary["comparison"] = compare(summary["a"], summary["b"])
    summary["per_iteration_input_reduction_pct"] = [
        item["comparison"]["input_token_reduction_pct"] for item in iterations
    ]
    return summary


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    a, b, cmp_ = summary["a"], summary["b"], summary["comparison"]
    variant = report.get("variant", "b1")
    b_only_keys = B_ONLY_KEYS + (B2_ONLY_KEYS if variant == "b2" else [])

    rows = [
        ("input tokens (合計)", "claude_total_input_tokens"),
        ("output tokens", "claude_output_tokens"),
        ("total tokens", "claude_total_tokens"),
        ("cost USD", "claude_cost_usd"),
        ("検索回数 (Grep/Glob+Bash)", "claude_grep_calls"),
        ("read 回数 (Read+Bash)", "claude_read_calls"),
        ("Bash 呼び出し回数", "claude_bash_calls"),
        ("読んだファイル数", "claude_file_count"),
        ("調査時間 (sec)", "wall_seconds"),
        ("カバレッジ", "coverage"),
    ]

    total_leaks = sum(
        item["a"].get("repo_leaks", 0) + item["b"].get("repo_leaks", 0)
        for item in report["iterations"]
    )

    lines = [
        "# Claude Code vs Claude Code + RepoScout",
        "",
        f"Model: {report['model']}",
        f"Variant: {variant} "
        + (
            "(B1 + Repository Files skeleton)"
            if variant == "b2"
            else "(plan + rg/read/git_log only)"
        ),
        f"Iterations: {summary['iterations']}",
        f"Snapshot: {report['snapshot']}",
        f"Repository leaks detected: {total_leaks} (0 が健全)",
        "",
        "## Summary (mean)",
        "",
        "| 指標 | A: Claude単独 | B: RepoScout利用 | 削減率 |",
        "| --- | ---: | ---: | ---: |",
    ]

    for label, key in rows:
        a_value = _value(a.get(key, 0))
        b_value = _value(b.get(key, 0))
        delta = "-"
        if a_value:
            delta = f"{round((a_value - b_value) / a_value * 100, 1)}%"
        lines.append(f"| {label} | {a_value} | {b_value} | {delta} |")

    lines.extend(
        [
            "",
            "## Distribution",
            "",
            "| 指標 | pattern | mean | median | min | max | stdev |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for label, key in rows:
        for pattern, block in (("A", a), ("B", b)):
            stats = block.get(key)
            if not isinstance(stats, dict):
                continue
            lines.append(
                f"| {label} | {pattern} | {stats['mean']} | {stats['median']} "
                f"| {stats['min']} | {stats['max']} | {stats['stdev']} |"
            )

    lines.extend(
        [
            "",
            "## RepoScout query outcomes (B only)",
            "",
            "| 指標 | mean | median | min | max | stdev |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for key in b_only_keys:
        stats = b.get(key)
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"| {key} | {stats['mean']} | {stats['median']} "
            f"| {stats['min']} | {stats['max']} | {stats['stdev']} |"
        )

    lines.extend(
        [
            "",
            "## Success criteria",
            "",
            f"- input token 削減率: {cmp_['input_token_reduction_pct']}% (目標 30%以上)",
            f"- total token 削減率: {cmp_['total_token_reduction_pct']}%",
            f"- read 回数 削減率: {cmp_['read_call_reduction_pct']}%",
            f"- 検索回数 削減率: {cmp_['search_call_reduction_pct']}%",
            f"- cost 削減率: {cmp_['cost_reduction_pct']}%",
            f"- 品質 (カバレッジ): A={_value(a['coverage'])} / B={_value(b['coverage'])}",
            f"- iteration別 input削減率: {summary['per_iteration_input_reduction_pct']}",
            "",
            "## Iterations",
            "",
        ]
    )

    for index, item in enumerate(report["iterations"], start=1):
        lines.extend(
            [
                f"### Iteration {index}",
                "",
                "| 指標 | A | B |",
                "| --- | ---: | ---: |",
            ]
        )
        for label, key in rows[:-1]:
            lines.append(
                f"| {label} | {item['a']['totals'].get(key, 0)} "
                f"| {item['b']['totals'].get(key, 0)} |"
            )
        lines.extend(
            [
                f"| カバレッジ | {item['a']['quality']['coverage']} "
                f"| {item['b']['quality']['coverage']} |",
                "",
                f"- Plan query数: {item['b']['plan_query_count']} "
                f"({item['b']['plan_tool_breakdown']})",
                f"- Query結果: 有効 {item['b']['totals']['effective_query_count']} / "
                f"失敗 {item['b']['totals']['failed_query_count']} "
                f"(read {item['b']['totals']['failed_read_count']}, "
                f"search {item['b']['totals']['failed_search_count']}) / "
                f"空 {item['b']['totals']['empty_evidence_count']}",
                f"- Fallback探索: read {item['b']['totals']['fallback_read_calls']}, "
                f"search {item['b']['totals']['fallback_search_calls']}",
                f"- RepoScout exit: {item['b']['reposcout']['exit_code']}, "
                f"evidence {item['b']['reposcout']['evidence_chars']} chars",
                f"- Repo leaks: A={item['a'].get('repo_leaks', 0)} "
                f"B={item['b'].get('repo_leaks', 0)}",
                f"- A missing: files={item['a']['quality']['missing_files']} "
                f"symbols={item['a']['quality']['missing_symbols']}",
                f"- B missing: files={item['b']['quality']['missing_files']} "
                f"symbols={item['b']['quality']['missing_symbols']}",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")


B3_KEYS = [
    "main_opus_input_tokens",
    "main_opus_output_tokens",
    "explorer_sonnet_input_tokens",
    "explorer_sonnet_output_tokens",
    "handoff_brief_chars",
    "evidence_pack_chars",
    "repository_files_count",
    "repository_files_chars",
    "explorer_tool_calls",
    "explorer_fallback_read_calls",
    "explorer_fallback_search_calls",
    "reposcout_query_count",
    "effective_query_count",
    "failed_query_count",
    "empty_evidence_count",
    "failed_read_count",
    "failed_search_count",
    "evidence_chars",
    "total_input_tokens",
    "total_output_tokens",
    "total_cost_usd",
    "wall_seconds",
]


def aggregate_b3(iterations: list[dict[str, Any]]) -> dict[str, Any]:
    """B3 has no A run in the same invocation; aggregate B3 alone.

    Compare the resulting numbers by hand against the fixed B1 N=5 baseline
    and the B2 N=1 result already on record — this run does not recompute them.
    """
    totals = [item["totals"] for item in iterations]
    summary: dict[str, Any] = {"iterations": len(iterations)}
    for key in B3_KEYS:
        summary[key] = describe([float(total.get(key, 0)) for total in totals])
    summary["coverage"] = describe([float(item["quality"]["coverage"]) for item in iterations])
    return summary


def write_markdown_b3(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    variant = report.get("variant", "b3")
    flow_label = B3_RUNNERS[variant][1]

    lines = [
        f"# {variant}: {flow_label}",
        "",
        f"Main model: {report['main_model']}",
        f"Explorer model: {report['explorer_model']}",
        f"Iterations: {summary['iterations']}",
        f"Snapshot: {report['snapshot']}",
        "",
        "RepoScout query/evidence logic is unchanged from B1/B2. Compare against "
        "the fixed B1 N=5 baseline and the B2 N=1 / B3 N=1 results recorded separately — "
        "this run does not recompute them.",
        "",
        "## Summary (mean)",
        "",
        "| 指標 | mean | median | min | max | stdev |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for key in B3_KEYS:
        stats = summary.get(key)
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"| {key} | {stats['mean']} | {stats['median']} "
            f"| {stats['min']} | {stats['max']} | {stats['stdev']} |"
        )

    coverage = summary["coverage"]
    lines.append(
        f"| coverage | {coverage['mean']} | {coverage['median']} "
        f"| {coverage['min']} | {coverage['max']} | {coverage['stdev']} |"
    )

    total_leaks = sum(item.get("repo_leaks", 0) for item in report["iterations"])
    lines.extend(
        [
            "",
            f"Repository leaks detected: {total_leaks} (0 が健全)",
            "",
            "## Iterations",
            "",
        ]
    )

    for index, item in enumerate(report["iterations"], start=1):
        totals = item["totals"]
        lines.extend(
            [
                f"### Iteration {index}",
                "",
                f"- Main(Opus) tokens: in={totals['main_opus_input_tokens']} "
                f"out={totals['main_opus_output_tokens']}",
                f"- Explorer(Sonnet) tokens: in={totals['explorer_sonnet_input_tokens']} "
                f"out={totals['explorer_sonnet_output_tokens']}",
                f"- handoff_brief_chars: {totals['handoff_brief_chars']}, "
                f"evidence_pack_chars: {totals['evidence_pack_chars']}",
                f"- Repository Files: {totals['repository_files_count']} files / "
                f"{totals['repository_files_chars']} chars",
                f"- Plan query数: {item['plan_query_count']} ({item['plan_tool_breakdown']})",
                f"- Query結果: 有効 {totals['effective_query_count']} / "
                f"失敗 {totals['failed_query_count']} "
                f"(read {totals['failed_read_count']}, search {totals['failed_search_count']}) / "
                f"空 {totals['empty_evidence_count']}",
                f"- Explorer tool_calls: {totals['explorer_tool_calls']} "
                f"(fallback read {totals['explorer_fallback_read_calls']}, "
                f"search {totals['explorer_fallback_search_calls']})",
                f"- total_input_tokens: {totals['total_input_tokens']}, "
                f"total_cost_usd: {totals['total_cost_usd']}, "
                f"wall_seconds: {totals['wall_seconds']}",
                f"- coverage: {item['quality']['coverage']}",
                f"- repo_leaks: {item.get('repo_leaks', 0)}",
                f"- missing: files={item['quality']['missing_files']} "
                f"symbols={item['quality']['missing_symbols']}",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")


B3_RUNNERS = {
    "b3": (run_pattern_b3, "Main(Opus) -> Explorer(Sonnet) -> RepoScout -> Explorer -> Main"),
    "b3.1": (run_pattern_b3_1, "Main(Opus) -> Explorer(Sonnet) -> RepoScout -> Main"),
}


def _run_b3(
    snapshot: Path, run_dir: Path, repo_root: Path, timestamp: str, repeat: int, pattern: str
) -> int:
    runner, flow_label = B3_RUNNERS[pattern]

    iterations: list[dict[str, Any]] = []
    for index in range(1, repeat + 1):
        print(f"--- iteration {index}/{repeat} ---")
        print(f"  [{pattern}] {flow_label} ...")
        result = runner(snapshot, run_dir, repo_root, index)
        totals = result["totals"]
        print(
            f"      main_opus tokens_in={totals['main_opus_input_tokens']} "
            f"out={totals['main_opus_output_tokens']} | "
            f"explorer_sonnet tokens_in={totals['explorer_sonnet_input_tokens']} "
            f"out={totals['explorer_sonnet_output_tokens']} | "
            f"total_in={totals['total_input_tokens']} "
            f"query有効={totals['effective_query_count']}/{totals['reposcout_query_count']} "
            f"explorer_tool_calls={totals['explorer_tool_calls']} "
            f"(read={totals['explorer_fallback_read_calls']} "
            f"search={totals['explorer_fallback_search_calls']}) "
            f"handoff={totals['handoff_brief_chars']}chars "
            f"pack={totals['evidence_pack_chars']}chars "
            f"leaks={result['repo_leaks']} "
            f"{totals['wall_seconds']}s"
        )
        iterations.append(result)

    report = {
        "variant": pattern,
        "main_model": MAIN_MODEL,
        "explorer_model": EXPLORER_MODEL,
        "snapshot": str(snapshot),
        "timestamp": timestamp,
        "iterations": iterations,
        "summary": aggregate_b3(iterations),
    }

    json_path = run_dir / "results.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path = run_dir / "results.md"
    write_markdown_b3(markdown_path, report)

    totals = report["summary"]
    print("")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    print(f"total_input_tokens: {totals['total_input_tokens']['mean']} (mean)")
    print(f"total_cost_usd: {totals['total_cost_usd']['mean']} (mean)")
    print(f"coverage: {totals['coverage']['mean']} (mean)")

    leaks = sum(item.get("repo_leaks", 0) for item in iterations)
    print(f"repo leaks: {leaks} (0 が健全)")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    parser.add_argument(
        "--pattern",
        choices=["b1", "b2", "b3", "b3.1"],
        default="b1",
        help=(
            "b1 = plan + rg/read/git_log only; b2 = b1 + Repository Files skeleton; "
            "b3 = Main(Opus)/Explorer(Sonnet) split on top of b2 (no A run, own report); "
            "b3.1 = b3 minus the Explorer synthesis call (Main reads raw RepoScout evidence)"
        ),
    )
    args = parser.parse_args()
    run_pattern = run_pattern_b2 if args.pattern == "b2" else run_pattern_b

    repo_root = args.repo_root.resolve()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = args.output or repo_root / "tests/experiments/results" / f"{timestamp}-comparison"
    run_dir.mkdir(parents=True, exist_ok=True)

    snapshot_root = args.snapshot_dir or Path(tempfile.gettempdir()) / "reposcout-comparison"
    snapshot = build_snapshot(repo_root, snapshot_root / timestamp / "target")
    print(f"Snapshot: {snapshot}")

    if args.pattern in ("b3", "b3.1"):
        return _run_b3(snapshot, run_dir, repo_root, timestamp, args.repeat, args.pattern)

    iterations: list[dict[str, Any]] = []
    for index in range(1, args.repeat + 1):
        print(f"--- iteration {index}/{args.repeat} ---")

        print("  [A] Claude alone ...")
        pattern_a = run_pattern_a(snapshot, run_dir, repo_root, args.model, index)
        print(
            f"      tokens_in={pattern_a['totals']['claude_total_input_tokens']} "
            f"out={pattern_a['totals']['claude_output_tokens']} "
            f"search={pattern_a['totals']['claude_grep_calls']} "
            f"read={pattern_a['totals']['claude_read_calls']} "
            f"leaks={pattern_a['repo_leaks']} "
            f"{pattern_a['totals']['wall_seconds']}s"
        )

        print(f"  [B/{args.pattern}] Claude + RepoScout ...")
        pattern_b = run_pattern(snapshot, run_dir, repo_root, args.model, index)
        skeleton_note = ""
        if args.pattern == "b2":
            skeleton_note = (
                f" files={pattern_b['totals']['repository_files_count']}"
                f"/{pattern_b['totals']['repository_files_chars']}chars"
            )
        print(
            f"      tokens_in={pattern_b['totals']['claude_total_input_tokens']} "
            f"out={pattern_b['totals']['claude_output_tokens']} "
            f"search={pattern_b['totals']['claude_grep_calls']} "
            f"read={pattern_b['totals']['claude_read_calls']} "
            f"query有効={pattern_b['totals']['effective_query_count']}"
            f"/{pattern_b['totals']['reposcout_query_count']} "
            f"fallback={pattern_b['totals']['fallback_read_calls']}r"
            f"+{pattern_b['totals']['fallback_search_calls']}s "
            f"leaks={pattern_b['repo_leaks']} "
            f"{pattern_b['totals']['wall_seconds']}s"
            f"{skeleton_note}"
        )

        iterations.append(
            {
                "a": pattern_a,
                "b": pattern_b,
                "comparison": compare(pattern_a["totals"], pattern_b["totals"]),
            }
        )

    report = {
        "model": args.model,
        "variant": args.pattern,
        "snapshot": str(snapshot),
        "timestamp": timestamp,
        "iterations": iterations,
        "summary": aggregate(iterations, variant=args.pattern),
    }

    json_path = run_dir / "results.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path = run_dir / "results.md"
    write_markdown(markdown_path, report)

    comparison = report["summary"]["comparison"]
    print("")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    print(f"input token reduction: {comparison['input_token_reduction_pct']}%")
    print(f"total token reduction: {comparison['total_token_reduction_pct']}%")
    print(f"read call reduction: {comparison['read_call_reduction_pct']}%")
    print(f"search call reduction: {comparison['search_call_reduction_pct']}%")
    print(f"cost reduction: {comparison['cost_reduction_pct']}%")
    print(f"per-iteration input reduction: {summary_reductions(report)}")

    leaks = sum(
        item["a"].get("repo_leaks", 0) + item["b"].get("repo_leaks", 0) for item in iterations
    )
    print(f"repo leaks: {leaks} (0 が健全)")

    return 0


def summary_reductions(report: dict[str, Any]) -> list[float | None]:
    return [item["comparison"]["input_token_reduction_pct"] for item in report["iterations"]]


if __name__ == "__main__":
    raise SystemExit(main())
