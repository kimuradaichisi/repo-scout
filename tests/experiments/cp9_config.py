"""CP9's two run configurations.

The permission model is CP8's, imported unchanged: the same Bash allowlist on
both sides, Write/Edit granted at the CLI to both because a subagent's usable
tools are the intersection of the CLI grant and its own declaration, and the
role gate hook deciding per caller who may actually write. CP9 changes the
task, not the harness that isolates the roles, so re-deriving any of that here
would only create a second copy that could drift from the one Step 0-B
verified.

What is CP9's own is the prompt: cp9_prompts adds the DECISION RECORD that
Decision Identity is read from.
"""

from dataclasses import dataclass
from typing import Any

from cp8_permissions import (
    config_a_allowed,
    config_a_disallowed,
    config_b_allowed,
    config_b_disallowed,
)
from cp9_prompts import render_config_a_prompt, render_config_b_prompt


@dataclass(frozen=True)
class RunConfig:
    key: str
    label: str
    is_delegating: bool
    allowed_tools: str
    disallowed_tools: str

    def render_prompt(self, task: dict[str, Any]) -> str:
        return render_config_b_prompt(task) if self.is_delegating else render_config_a_prompt(task)


CONFIG_A = RunConfig(
    key="config_a",
    label="Main-Opus-Sole",
    is_delegating=False,
    allowed_tools=config_a_allowed(),
    disallowed_tools=config_a_disallowed(),
)

CONFIG_B = RunConfig(
    key="config_b",
    label="Main-Opus+Sonnet-Worker",
    is_delegating=True,
    allowed_tools=config_b_allowed(),
    disallowed_tools=config_b_disallowed(),
)
