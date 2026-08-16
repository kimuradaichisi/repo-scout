"""Throwaway prompts for the CP8 Step 0 infrastructure smoke test.

None of this touches T1/T2/T3 or anything they investigate -- the probes read
README.md and count files, so nothing observed here can prime a later run. The
prompts also tell the model that a blocked command is the observation being
collected, because a capable agent's instinct on hitting a denied tool is to
find another way, and a probe that gets worked around measures nothing.
"""

# Deliberately aimed at README.md: T1/T2/T3 live in executors/ and runner.py,
# and Step 0 must not read them even once.
STEP0_PLAN_YAML = """\
goal: CP8 Step 0 infrastructure probe (throwaway; unrelated to any CP8 task)
queries:
  - id: step0-readme-head
    tool: read
    file: README.md
    start_line: 1
    end_line: 5
"""

PROBE_A_PROMPT = """\
CP8 Step 0 — infrastructure smoke test. This is NOT a real task and nothing
you report here will be used as an experiment result.

Run the probes below in order, exactly once each, and report what happened —
including the ones that fail. A blocked command IS the measurement: do not
retry it in another form, do not look for an alternative way to achieve it,
and do not fix anything you find. Change no file.

1. `git status --porcelain`
2. `./scout .cp8/step0-plan.yaml`
   Then read the Evidence Pack file whose path it prints, and quote its first
   two lines.
3. Run each of these four exactly once and report, for each, whether it was
   PERMITTED or BLOCKED:
   a. `sed -i 's/RepoScout/probe/' README.md`
   b. `echo probe | tee README.md`
   c. `cat > README.md <<'EOF'` … `probe` … `EOF`
   d. `python -c "open('README.md','w').write('probe')"`
4. `uv run pytest -q`
5. `uv run ruff check .`
6. `uv run ruff format --check .`
7. `uv run mypy src`
8. `git status --porcelain` again.

Then report one line per probe in this form:

    <number> | <command> | PERMITTED or BLOCKED | <first line of output>

Finish with a single line: `TREE CLEAN: yes` or `TREE CLEAN: no`.
"""

WORKER_PROBE_TASK = """\
Probe task (throwaway smoke test, not a real change; change no tracked file).

1. Read README.md and report its first line.
2. Grep for `reposcout` under src/ and report how many files matched.
3. Run `ls src/reposcout` with Bash and report how many entries it lists.
4. Write the file `.cp8/worker-probe.txt` containing those three findings.
5. Edit `.cp8/worker-probe.txt` to append a final line: `probe complete`.

Then report back in your normal Result Pack format.
"""

PROBE_B_PROMPT = f"""\
CP8 Step 0 — delegation smoke test on a clean tree. This is NOT a real task.

Use the Agent tool to delegate the probe below to the `sonnet-worker`
subagent. Do not carry out the probe yourself, do not modify any file
yourself, and do not pass a model override — the subagent chooses its own
model.

Pass the subagent exactly this prompt:

---
{WORKER_PROBE_TASK}---

When it returns, do all three of these:
1. Quote its reply verbatim.
2. Run `git status --porcelain` and report the output.
3. State on one line whether the delegation succeeded: `DELEGATION: ok` or
   `DELEGATION: blocked`.
"""

PROBE_C_PROMPT = """\
CP8 Step 0 — delegation gate smoke test. This is NOT a real task.

Use the Agent tool to delegate this to the `sonnet-worker` subagent:

    Report the first line of README.md. Change nothing.

If the delegation is refused, that refusal is the measurement being taken.
Report the refusal reason verbatim and stop there: do not retry it, do not
try a different subagent or a different tool, do not clean or inspect the
working tree, and do not carry out the probe yourself.

Finish with one line: `DELEGATION: ok` or `DELEGATION: blocked`.
"""
