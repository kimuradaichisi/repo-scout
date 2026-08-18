"""The two Step 1 run configurations, as data rather than branching code.

Config A and Config B differ in exactly the ways rev.2's design fixed:
prompt, tool grant/denial, and whether Write/Edit route through the role
gate. Expressing that as one small object per config, rather than `if
config == "b"` scattered through the runner, is what keeps run_cp8_step1.py
from re-deriving the difference at every call site.
"""

from dataclasses import dataclass
from typing import Any

from cp8_permissions import (
    config_a_allowed,
    config_a_disallowed,
    config_b_allowed,
    config_b_disallowed,
)
from cp8_step1_prompts import render_config_a_prompt, render_config_b_prompt


@dataclass(frozen=True)
class StepConfig:
    key: str
    label: str
    is_delegating: bool
    allowed_tools: str
    disallowed_tools: str

    def render_prompt(self, task: dict[str, Any]) -> str:
        return render_config_b_prompt(task) if self.is_delegating else render_config_a_prompt(task)


CONFIG_A = StepConfig(
    key="config_a",
    label="Main-Opus-Sole",
    is_delegating=False,
    allowed_tools=config_a_allowed(),
    disallowed_tools=config_a_disallowed(),
)

CONFIG_B = StepConfig(
    key="config_b",
    label="Main-Opus+Sonnet-Worker",
    is_delegating=True,
    allowed_tools=config_b_allowed(),
    disallowed_tools=config_b_disallowed(),
)
