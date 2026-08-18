"""C0 vs C1 comparison. N=1: vocabulary is deliberately limited (see _interpret)."""

from typing import Any

INTERPRETATIONS = ("observed reduction", "no observed reduction", "mixed", "measurement invalid")


def _run_ok(report: dict[str, Any]) -> bool:
    return report["run"]["exit_code"] == 0 and not report["run"]["error"]


def _interpret(p0: dict[str, int], p1: dict[str, int], quality_parity: bool, runs_ok: bool) -> str:
    if not runs_ok:
        return "measurement invalid"
    reduced = [
        p1["repeated_read_calls"] < p0["repeated_read_calls"],
        p1["repeated_source_bytes"] < p0["repeated_source_bytes"],
        p1["total_input_tokens"] < p0["total_input_tokens"],
    ]
    if not quality_parity:
        return "mixed"
    if all(reduced):
        return "observed reduction"
    if not any(reduced):
        return "no observed reduction"
    return "mixed"


def compare(control: dict[str, Any], pack_first: dict[str, Any]) -> dict[str, Any]:
    p0, p1 = control["primary_metrics"], pack_first["primary_metrics"]
    s0, s1 = control["secondary_metrics"], pack_first["secondary_metrics"]
    quality_parity = (
        control["quality"]["quality_floor_met"] and pack_first["quality"]["quality_floor_met"]
    )
    runs_ok = _run_ok(control) and _run_ok(pack_first)

    return {
        "repeated_read_calls_delta": p1["repeated_read_calls"] - p0["repeated_read_calls"],
        "repeated_source_bytes_delta": p1["repeated_source_bytes"] - p0["repeated_source_bytes"],
        "total_input_tokens_delta": p1["total_input_tokens"] - p0["total_input_tokens"],
        "cost_usd_delta": round(s1["cost_usd"] - s0["cost_usd"], 6),
        "elapsed_seconds_delta": round(s1["elapsed_seconds"] - s0["elapsed_seconds"], 3),
        "quality_parity": quality_parity,
        "runs_ok": runs_ok,
        "interpretation": _interpret(p0, p1, quality_parity, runs_ok),
    }
