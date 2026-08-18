"""Assembles one run's full M5 report from its transcript and ClaudeRun.

Primary metrics (repeated_read_calls / repeated_source_bytes / total input
tokens) and secondary metrics are computed independently, then combined --
nothing here re-derives quality from the primary metrics or vice versa.
"""

from pathlib import Path
from typing import Any

from claude_metrics import ClaudeRun
from cp7_metrics import score_generic
from cp8_transcript import load_events
from m5_pack_calls import (
    final_direct_reads_after_pack,
    pack_call_count,
    pack_call_metrics,
    reposcout_call_count,
)
from m5_read_analysis import fictional_read_paths, read_events, repeat_metrics, unique_read_paths
from m5_task import TASK
from run_comparison import count_repo_leaks

from reposcout.skeleton import RepositorySkeleton

QUALITY_FLOOR_COVERAGE = 1.0


def _secondary_metrics(
    run: ClaudeRun, reads: list[Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "total_tokens": run.total_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": round(run.cost_usd, 6),
        "elapsed_seconds": round(run.wall_seconds, 3),
        "read_calls": len(reads),
        "unique_read_paths": unique_read_paths(reads),
        "search_calls": run.grep_calls,
        "reposcout_calls": reposcout_call_count(events),
        "pack_calls": pack_call_count(events),
        **pack_call_metrics(events),
        "final_direct_reads_after_pack": final_direct_reads_after_pack(events),
    }


def _quality(run: ClaudeRun) -> dict[str, Any]:
    quality = score_generic(run.final_text, TASK)
    return {
        "coverage": quality["coverage"],
        "found_files": quality["found_files"],
        "missing_files": quality["missing_files"],
        "found_symbols": quality["found_symbols"],
        "missing_symbols": quality["missing_symbols"],
        "quality_floor_met": quality["coverage"] >= QUALITY_FLOOR_COVERAGE,
    }


def build_report(
    condition: str,
    run: ClaudeRun,
    transcript: Path,
    snapshot: Path,
    harness_repo_root: Path,
) -> dict[str, Any]:
    events = load_events(transcript)
    reads = read_events(events, snapshot)
    tracked = RepositorySkeleton().list_files(snapshot)

    return {
        "condition": condition,
        "primary_metrics": {
            **repeat_metrics(reads),
            "total_input_tokens": run.total_input_tokens,
        },
        "secondary_metrics": _secondary_metrics(run, reads, events),
        "quality": _quality(run),
        "safety": {
            "fictional_paths": fictional_read_paths(reads, tracked),
            "repo_leaks": count_repo_leaks(transcript, harness_repo_root),
        },
        "run": {
            "exit_code": run.exit_code,
            "error": run.error,
            "transcript_path": str(transcript),
        },
    }
