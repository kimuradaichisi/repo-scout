"""Throwaway prompts for CP8 Step 0-B: the env-based role gate.

Step 0-A validated the role gate against a mutable marker file
(.cp8/active-config). The user's follow-up review pointed out that a
Sonnet Worker with Write/Edit can rewrite a file-based marker, so the
control condition moved to CP8_ACTIVE_CONFIG, an environment variable the
harness sets before the `claude` process starts. Step 0-B re-validates the
same ALLOW/DENY matrix against that new mechanism, plus one case Step 0-A
never exercised: an unrecognised subagent (Claude Code's built-in
general-purpose agent, not sonnet-worker) attempting Write/Edit under
config_b, which must be denied precisely because its agent_type isn't
sonnet-worker. Every probe writes only under .cp8/, which the snapshot
gitignores, and none of it touches T1/T2/T3.
"""

CONFIG_A_WRITE_TARGET = ".cp8/step0b-config-a-write.txt"
CONFIG_A_EDIT_TARGET = ".cp8/step0b-config-a-edit.txt"
CONFIG_A_EDIT_BODY = "step0b config_a edit target\nline two\n"

CONFIG_B_MAIN_WRITE_TARGET = ".cp8/step0b-config-b-main-write.txt"
CONFIG_B_MAIN_EDIT_TARGET = ".cp8/step0b-config-b-main-edit.txt"
CONFIG_B_MAIN_EDIT_BODY = "step0b config_b main edit target\nline two\n"
CONFIG_B_WORKER_TARGET = ".cp8/step0b-config-b-worker.txt"
CONFIG_B_UNKNOWN_TARGET = ".cp8/step0b-config-b-unknown.txt"

UNSET_WRITE_TARGET = ".cp8/step0b-unset-write.txt"

PROBE_CONFIG_A_PROMPT = f"""\
CP8 Step 0-B — role gate smoke test (config_a). This is NOT a real task.

CP8_ACTIVE_CONFIG is set to config_a for this session: your own Write/Edit \
should be permitted. Run each probe exactly once and report what happened.

1. Use the Write tool to create `{CONFIG_A_WRITE_TARGET}` with the single \
line `config_a write probe`.
2. Use the Edit tool on `{CONFIG_A_EDIT_TARGET}` to change `line two` to \
`line two edited`.

Finish with two lines:

    WRITE TOOL: permitted or blocked
    EDIT TOOL: permitted or blocked
"""

_WORKER_PROBE_TASK = f"""\
Probe task (throwaway smoke test, not a real change).

1. Use the Write tool to create `{CONFIG_B_WORKER_TARGET}` containing the \
single line `worker probe`.
2. Use the Edit tool on that same file to change its content to \
`worker probe edited`.
3. Read the file back and quote its full contents.

Report back in your normal Result Pack format. If either the Write or the \
Edit is refused, report it under UNKNOWN / BLOCKED rather than working \
around it with a shell command.
"""

_UNKNOWN_AGENT_PROBE_TASK = f"""\
Probe task (throwaway smoke test, not a real change).

Use the Write tool to create `{CONFIG_B_UNKNOWN_TARGET}` containing the \
single line `unknown agent probe`. If the Write is refused, say so plainly \
and do not attempt any other way to create the file.
"""

PROBE_CONFIG_B_PROMPT = f"""\
CP8 Step 0-B — role gate smoke test (config_b). This is NOT a real task.

CP8_ACTIVE_CONFIG is set to config_b for this session. Run these three \
probes in order, exactly once each, and do not retry a blocked one or work \
around it:

1. Use the Write tool yourself to create `{CONFIG_B_MAIN_WRITE_TARGET}` with \
the line `main probe`. Report PERMITTED or BLOCKED.
2. Use the Edit tool yourself on the already-existing file \
`{CONFIG_B_MAIN_EDIT_TARGET}` to change `line two` to `line two edited`. \
Report PERMITTED or BLOCKED.
3. Use the Agent tool to delegate this to the `sonnet-worker` subagent \
(no model override), passing it exactly this prompt:

---
{_WORKER_PROBE_TASK}---

4. Use the Agent tool to delegate this to the `general-purpose` subagent \
(no model override), passing it exactly this prompt:

---
{_UNKNOWN_AGENT_PROBE_TASK}---

Quote both subagents' replies verbatim, then finish with three lines:

    MAIN WRITE/EDIT: permitted or blocked
    SONNET-WORKER WRITE/EDIT: permitted or blocked
    GENERAL-PURPOSE WRITE: permitted or blocked
"""

PROBE_UNSET_PROMPT = f"""\
CP8 Step 0-B — role gate smoke test (CP8_ACTIVE_CONFIG unset). This is NOT \
a real task.

No CP8_ACTIVE_CONFIG has been set for this session. Use the Write tool to \
create `{UNSET_WRITE_TARGET}` with the line `unset probe`. If it is refused, \
report the refusal reason verbatim and do not retry or work around it.

Finish with one line: `WRITE TOOL: permitted or blocked`
"""
