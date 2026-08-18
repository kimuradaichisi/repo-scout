"""CP9 prompts. Same wording to both configs, plus a required DECISION RECORD.

The task text, the acceptance criteria and the report shape are identical
across Config A and Config B, so an outcome difference traces to who
implemented rather than to what was asked. What CP9 adds to CP8's prompt shape
is the DECISION RECORD: four fixed one-liners naming the design choice that
was made. Without it there is no way to show that S and L resolved the same
judgement, and "we varied volume, not uncertainty" stays an assumption.

The record is asked for before the free-form DECISIONS section on purpose. It
is a label for what was chosen, not the argument for it -- the argument still
goes in DECISIONS, and the run is not asked to compress its reasoning into
four lines.
"""

from typing import Any

from cp8_packs import IMPLEMENTATION_PACK_TEMPLATE
from cp9_decision import allowed_values_block
from cp9_tasks import render_acceptance_criteria, render_goal

MAIN_REPORT_SECTIONS = (
    "DECISION RECORD",
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

DECISION_RECORD_BLOCK = f"""\
## DECISION RECORD
Exactly these four lines. Each value must be copied verbatim from the list \
below — one value per line, nothing else on the line, no prose, no \
parentheses, no explanation. The allowed values are:

{allowed_values_block()}

Write them as:

domain_model_representation: <value>
measurement_responsibility: <value>
compatibility_strategy: <value>
propagation_strategy: <value>

RATIONALE:
Free text, any language: why you chose those four values, and what you \
rejected. Write as much as you need here — this section is read by people, \
not matched by the harness.
"""

SCRATCH_POLICY = """\
Do not create scratch, temporary, helper or smoke-test files inside the \
repository. If you need one, write it under /tmp with an absolute path. Any \
file left in the repository that is not one of this task's declared targets \
counts as a scope violation, including a file you emptied but could not \
delete."""

CONFIG_A_PROMPT = """\
You are implementing a change to this repository end to end. There is no \
reviewer after you and no one to hand this off to — investigate, decide, \
implement, test, and verify the quality gates yourself.

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

{scratch_policy}

Finish with a report in exactly this format and nothing else:

{decision_record}
## DECISIONS
Why you chose what the DECISION RECORD names, including any alternative you \
rejected.

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
2. Decide the design, including every judgement call the task leaves open, \
and write it down. This is your decision, not the Worker's: the Worker \
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

{scratch_policy}

6. Finish with a report in exactly this format and nothing else:

{decision_record}
## DECISIONS
Why you chose what the DECISION RECORD names, including any alternative you \
rejected.

## CHANGED FILES
One path per line.

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
        goal=render_goal(task),
        criteria=render_acceptance_criteria(task),
        gates=_GATE_LIST,
        decision_record=DECISION_RECORD_BLOCK,
        scratch_policy=SCRATCH_POLICY,
    )


def render_config_b_prompt(task: dict[str, Any]) -> str:
    return CONFIG_B_MAIN_PROMPT.format(
        goal=render_goal(task),
        criteria=render_acceptance_criteria(task),
        pack_template=IMPLEMENTATION_PACK_TEMPLATE,
        gates=_GATE_LIST,
        decision_record=DECISION_RECORD_BLOCK,
        scratch_policy=SCRATCH_POLICY,
    )
