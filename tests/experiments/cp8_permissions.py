"""Tool permissions for CP8 Config A and Config B.

The two configs are meant to differ in exactly one thing: who writes the code.
Everything else that could plausibly change how much work gets done -- above
all how freely Main may reach for a shell -- is held identical, so Bash is the
same allowlist on both sides. Both CLIs grant Write/Edit (Step 0 found a
subagent's usable tools are the intersection of the CLI grant and its own
declaration, so denying Write/Edit on the CLI denies the Worker too); the
actual difference is delegation and who the role gate lets write:

    Config A   delegation denied     role gate irrelevant, Main writes directly
    Config B   delegation allowed    role gate denies Main's writes, allows the Worker's

Bash is an allowlist rather than a blanket grant because a blanket grant would
hand Config B's Main a write path (`sed -i`, `tee`, a heredoc, `python -c`)
that the missing Write tool is there to close. `ruff format` is absent for the
same reason -- it edits files -- while `ruff format --check` is present.
"""

# Claude Code renamed the delegation tool Task -> Agent. Both names are listed
# wherever delegation is granted or denied, so a run is not quietly measuring a
# permission that no longer exists under the name it was written down as.
DELEGATION_TOOLS = ("Agent", "Task")

BASH_ALLOWLIST = (
    "Bash(./scout:*)",
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git ls-files:*)",
    "Bash(uv run pytest:*)",
    "Bash(uv run ruff check:*)",
    "Bash(uv run ruff format --check:*)",
    "Bash(uv run mypy:*)",
)

READ_TOOLS = ("Read", "Grep", "Glob", "TodoWrite")
WRITE_TOOLS = ("Write", "Edit")
NEVER_ALLOWED = ("NotebookEdit", "WebFetch", "WebSearch")


def _join(*groups: tuple[str, ...]) -> str:
    return ",".join(item for group in groups for item in group)


def config_a_allowed() -> str:
    """Main implements directly: read tools, the shared Bash allowlist, Write/Edit."""
    return _join(READ_TOOLS, BASH_ALLOWLIST, WRITE_TOOLS)


def config_a_disallowed() -> str:
    """Delegation is denied under both tool names, so Config A cannot become Config B."""
    return _join(DELEGATION_TOOLS, NEVER_ALLOWED)


def config_b_allowed() -> str:
    """Main delegates: read tools, the shared Bash allowlist, delegation, Write/Edit.

    Write/Edit are granted here and refused per-caller by the role gate hook
    (.claude/hooks/role_gate.py). Step 0 measured why: a subagent's usable tools
    are the intersection of this grant and its own declaration, so withholding
    Write/Edit from Main withheld them from the Worker too, and Config B had
    nobody left who could implement. The grant is what makes the Worker able to
    write; the hook is what keeps Main unable to.
    """
    return _join(READ_TOOLS, BASH_ALLOWLIST, DELEGATION_TOOLS, WRITE_TOOLS)


def config_b_disallowed() -> str:
    """Only the tools no config ever uses. Main's write ban lives in the hook."""
    return _join(NEVER_ALLOWED)
