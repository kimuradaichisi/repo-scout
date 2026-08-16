"""Prompts for CP8 Step 1: Config A (Main-Opus-Sole) and Config B (Main + Worker).

Both configs receive the same task goal and the same acceptance criteria,
worded identically, so a difference in outcome traces to who implements, not
to what was asked. Both are told to end with a report using the same section
names (DECISIONS / CHANGED FILES / TEST RESULTS / QUALITY GATE RESULTS /
SUMMARY) so the grader in cp8_step1_grader.py reads a comparable artifact from
either config, and REVIEW is Config B's own addition on top of that shared
shape rather than a different shape.

CLAUDE.md is not pasted into the prompt -- it is present in the snapshot at
the paths Main investigates, exactly where a real contributor would find it.
"""

from typing import Any

from cp8_packs import IMPLEMENTATION_PACK_TEMPLATE
from cp8_tasks import render_acceptance_criteria

MAIN_REPORT_SECTIONS = (
    "DECISIONS",
    "CHANGED FILES",
    "TEST RESULTS",
    "QUALITY GATE RESULTS",
    "REVIEW",
    "SUMMARY",
)

QUALITY_GATE_COMMANDS = (
    "uv run pytest -q",
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run mypy src",
)

_GATE_LIST = "\n".join(f"    {cmd}" for cmd in QUALITY_GATE_COMMANDS)

CONFIG_A_PROMPT = """\
You are implementing a small, well-scoped change to this repository end to \
end. There is no reviewer after you and no one to hand this off to — \
investigate, decide, implement, test, and verify the quality gates yourself.

## TASK
{goal}

## ACCEPTANCE CRITERIA
{criteria}

Read CLAUDE.md at the repository root before you touch anything; it is \
binding for any code you write, including its size and responsibility \
limits. Investigate live — read the actual source, don't assume its \
behaviour. Add or edit tests as the acceptance criteria require. When you \
believe the change is complete, run these four gates yourself, exactly as \
written, and report their real output:
{gates}
Never report a gate you did not run, and never report green for one that \
failed.

Finish with a report in exactly this format and nothing else:

## DECISIONS
The design choices you made, and why. Write `(none required)` only if the \
task genuinely left no open choice.

## CHANGED FILES
One path per line.

## TEST RESULTS

## QUALITY GATE RESULTS

## SUMMARY
"""

CONFIG_B_MAIN_PROMPT = """\
You are the Main investigator and reviewer for a change to this repository. \
You do not implement it yourself: Write and Edit are refused to you \
structurally, by a hook, regardless of what you try. The `sonnet-worker` \
subagent implements the change; you reach it through the Agent tool.

## TASK
{goal}

## ACCEPTANCE CRITERIA
{criteria}

Do this, in order:

1. Read CLAUDE.md at the repository root, then investigate the repository \
live — read the actual source — until you know exactly what must change and \
why. Do not guess at behaviour you have not read.
2. Decide the design, including any judgement call the task leaves open, and \
write it down. This is your decision, not the Worker's: the Worker \
implements what you decide and does not revisit it.
3. Write an Implementation Pack using exactly this structure, and hand it to \
the sonnet-worker subagent through the Agent tool:

{pack_template}

4. When the Worker returns its Result Pack, review it — do not accept it on \
its word:
   - Independently re-run the same four gates yourself via Bash and compare \
your own results against what the Worker's QUALITY GATE RESULTS section \
claims:
{gates}
   - Run `git diff --stat` and confirm every changed file is one you named \
in TARGET FILES.
   - Check the Result Pack against every item in ACCEPTANCE CRITERIA.
5. If the Result Pack falls short — gates disagree, scope exceeded, a \
criterion unmet, or a BLOCKED item you can now resolve — you may send ONE \
corrective Implementation Pack to a fresh sonnet-worker invocation. Not more \
than one: after a second attempt, accept the outcome and report the \
shortfall rather than trying again.
6. Finish with a report in exactly this format and nothing else:

## DECISIONS

## CHANGED FILES

## TEST RESULTS

## QUALITY GATE RESULTS
Your own independently re-run results — not the Worker's claim.

## REVIEW
State explicitly: did your independent gate results match the Worker's \
claim? did the diff stay within TARGET FILES? how many Implementation Packs \
did you send, 1 or 2?

## SUMMARY
"""


def render_config_a_prompt(task: dict[str, Any]) -> str:
    return CONFIG_A_PROMPT.format(
        goal=task["goal"], criteria=render_acceptance_criteria(task), gates=_GATE_LIST
    )


def render_config_b_prompt(task: dict[str, Any]) -> str:
    return CONFIG_B_MAIN_PROMPT.format(
        goal=task["goal"],
        criteria=render_acceptance_criteria(task),
        pack_template=IMPLEMENTATION_PACK_TEMPLATE,
        gates=_GATE_LIST,
    )
