"""Independent acceptance-criteria grader for CP8 Step 1.

Whether a diff satisfies criteria like "context 5 is asserted for 1-3 paths"
is a semantic question about test content, not a fact `git diff --name-only`
can answer -- CLAUDE.md's own guidance is to spend reasoning exactly where
that judgement is required, so this is the one LLM call in Step 1 that is
neither Main nor the Worker: a fresh, tool-less Opus call that sees the task,
the criteria, and the diff, and has no way to know which config produced it.
Grading is done once per run rather than by either party marking its own
work.
"""

import re
from pathlib import Path
from typing import Any

import yaml
from claude_metrics import run_claude
from cp8_tasks import render_acceptance_criteria
from run_comparison import MAIN_MODEL, NO_TOOLS_DISALLOWED

GRADER_PROMPT = """\
You are grading an already-finished code change against a fixed checklist. \
You did not write it. Grade only what is in front of you — do not infer \
intent beyond what the diff shows.

## TASK GOAL
{goal}

## ACCEPTANCE CRITERIA
{criteria}

## DIFF
```diff
{diff}
```

## GATE OUTPUT REPORTED BY THE IMPLEMENTER
{gate_output}

For each acceptance criterion above, decide MET, NOT_MET, or UNKNOWN. Use \
UNKNOWN only when the diff genuinely does not contain enough information to \
judge it — never as a hedge. Then give the overall verdict: true only if \
every criterion is MET.

Answer in exactly this YAML and nothing else:

criteria:
  - text: "<criterion text, verbatim>"
    verdict: MET
    reason: "<one sentence>"
overall_met: true
"""


def render_grader_prompt(task: dict[str, Any], diff: str, gate_output: str) -> str:
    return GRADER_PROMPT.format(
        goal=task["goal"],
        criteria=render_acceptance_criteria(task),
        diff=diff or "(no diff — no files were changed)",
        gate_output=gate_output or "(not reported)",
    )


def _extract_yaml(text: str) -> str:
    fenced = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    return max(fenced, key=len).strip() if fenced else text.strip()


def parse_grade(text: str) -> dict[str, Any]:
    """Parse the grader's YAML; a malformed reply grades as ungraded, not passing."""
    try:
        parsed = yaml.safe_load(_extract_yaml(text))
    except yaml.YAMLError:
        parsed = None
    if not isinstance(parsed, dict) or "overall_met" not in parsed:
        return {"overall_met": False, "criteria": [], "parse_error": True, "raw": text}
    criteria = parsed.get("criteria", [])
    return {
        "overall_met": bool(parsed.get("overall_met")),
        "criteria": criteria if isinstance(criteria, list) else [],
        "parse_error": False,
    }


def grade_run(
    task: dict[str, Any], diff: str, gate_output: str, snapshot: Path, transcript_path: Path
) -> dict[str, Any]:
    """Run the blind grader call and return its parsed verdict plus call metrics."""
    run = run_claude(
        render_grader_prompt(task, diff, gate_output),
        label=f"CP8-step1-grader-{task['key']}",
        root=snapshot,
        transcript_path=transcript_path,
        model=MAIN_MODEL,
        allowed_tools="",
        disallowed_tools=NO_TOOLS_DISALLOWED,
    )
    grade = parse_grade(run.final_text)
    grade["call"] = {
        "input_tokens": run.total_input_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": round(run.cost_usd, 6),
        "elapsed_seconds": round(run.wall_seconds, 3),
    }
    return grade
