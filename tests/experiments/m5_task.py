"""M5's task and prompts. No new task: reuses CP7's change_scope task verbatim.

Change Scope was picked because it requires reading multiple sources
(the constants' definition site, the executor, its sole caller) -- the
"複数sourceを読む必要があるもの" the instructions ask for -- and its ground
truth (cp7_tasks.py) is unchanged by M1-M4: ripgrep.py's CONTEXT_LINES /
NARROW_PATH_THRESHOLD still have no dedicated test file.

M5 is single-agent (Main only, no Explorer/planner split), so only the task's
semantic content -- goal, confirmation points, ground truth -- is reused.
CP7's planner_route / plan_policy fields belong to the retired B3.2
architecture and are not part of this task's identity.
"""

from pathlib import Path

from cp7_tasks import TASKS

TASK = next(item for item in TASKS if item["key"] == "change_scope")

POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "pack_first_policy.md"


def _confirmation_block() -> str:
    return "\n".join(f"- {point}" for point in TASK["confirmation_points"])


def control_prompt() -> str:
    return f"""\
{TASK["investigation_goal"]}

確認対象:
{_confirmation_block()}

実装はしないでください。
"""


def pack_first_prompt() -> str:
    policy = POLICY_PATH.read_text(encoding="utf-8")
    return f"""\
{control_prompt()}
--- Pack First Policy ---
{policy}

利用可能なコマンド(Bashから直接実行できます):
- reposcout skeleton --root .
- reposcout pack <request-file> --root .

pack request fileの形式(YAML):
ranges:
  - path: <tracked file path>
    start_line: <int>
    end_line: <int>

request fileはrepository内に作らず、/tmp 等の外部へ書いてください。
"""
