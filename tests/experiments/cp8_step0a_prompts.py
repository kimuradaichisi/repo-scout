"""Throwaway prompts for CP8 Step 0-A, the role-aware Write/Edit gate check.

Everything here writes to scratch files under .cp8/, which the snapshot
gitignores: the probes exercise writing without dirtying the tree, so the
pre_worker_diff_empty gate stays satisfied and the two gates can be observed
independently rather than tripping over each other. Nothing here reads
anything T1/T2/T3 touches.
"""

MAIN_EDIT_TARGET = ".cp8/main-edit-target.txt"
MAIN_WRITE_TARGET = ".cp8/main-write-probe.txt"
WORKER_WRITE_TARGET = ".cp8/worker-write-probe.txt"

MAIN_EDIT_TARGET_BODY = "cp8 step0-a main edit target\nline two\n"

PROBE_MAIN_PROMPT = f"""\
CP8 Step 0-A — role gate smoke test. This is NOT a real task, and nothing here
relates to any CP8 implementation task.

Run the probes below in order, exactly once each, and report what happened —
including the ones that fail. A blocked attempt IS the measurement: do not
retry it, do not reach for another tool or another phrasing to accomplish the
same thing, and do not fix anything you notice along the way.

1. Use the Write tool to create `{MAIN_WRITE_TARGET}` with the single line
   `main probe`.
2. Use the Edit tool on `{MAIN_EDIT_TARGET}` to change `line two` to
   `line two edited`.
3. Run each of these four Bash commands exactly once, reporting PERMITTED or
   BLOCKED for each:
   a. `sed -i 's/target/probe/' {MAIN_EDIT_TARGET}`
   b. `echo probe | tee {MAIN_WRITE_TARGET}`
   c. `cat > {MAIN_WRITE_TARGET} <<'EOF'` … `probe` … `EOF`
   d. `python -c "open('{MAIN_WRITE_TARGET}','w').write('probe')"`
4. Run each of these six commands exactly once, as written, with nothing
   appended and nothing chained onto them:
   a. `./scout .cp8/step0-plan.yaml`
   b. `git status --porcelain`
   c. `git diff --stat`
   d. `git ls-files src`
   e. `uv run pytest -q`
   f. `uv run ruff check .`
5. Run `uv run ruff format --check .` and then `uv run mypy src`, each on its
   own, unchained.

Report one line per probe:

    <number> | <tool or command> | PERMITTED or BLOCKED | <first line of output
    or of the block reason>

Finish with two lines:

    WRITE TOOL: permitted or blocked
    EDIT TOOL: permitted or blocked
"""

WORKER_PROBE_TASK = f"""\
Probe task (throwaway smoke test, not a real change).

1. Use the Write tool to create `{WORKER_WRITE_TARGET}` containing exactly
   these two lines:

       worker probe
       status: initial

2. Use the Edit tool on `{WORKER_WRITE_TARGET}` to change `status: initial`
   to `status: edited`.
3. Read the file back and quote its full contents.

Then report back in your normal Result Pack format. If either the Write or the
Edit is refused, report it under UNKNOWN / BLOCKED rather than working around
it with a shell command.
"""

PROBE_DELEGATE_PROMPT = f"""\
CP8 Step 0-A — delegated write smoke test on a clean tree. This is NOT a real
task.

Use the Agent tool to delegate the probe below to the `sonnet-worker`
subagent. Do not carry out the probe yourself, do not write or edit any file
yourself, and do not pass a model override.

Pass the subagent exactly this prompt:

---
{WORKER_PROBE_TASK}---

When it returns, do all three of these:
1. Quote its reply verbatim.
2. Run `git status --porcelain` and report the output.
3. Finish with one line: `WORKER WRITE: ok` or `WORKER WRITE: blocked`.
"""
