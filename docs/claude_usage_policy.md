# RepoScout Usage Policy (for Claude)

For a Strong Model (Claude or another caller) investigating a repository RepoScout has
access to: prefer RepoScout's deterministic path over repeatedly Reading/Globbing/Searching
the repository directly. Nothing here makes RepoScout an LLM-dependent component --
RepoScout stays deterministic; this document is about how a *caller* should sequence its
own tool use around it.

## 1. Skeleton First

Before repeated individual Glob/Read/List calls to learn what a repository contains, call
`reposcout skeleton` once. It is the deterministic source of truth for "what paths exist" --
a plan built from it can't name a path that doesn't.

## 2. Deterministic Search First

Do not guess these from memory or prior training data -- get them from RepoScout/the
underlying tool instead:

- path existence (`reposcout skeleton`)
- literal / pattern search (`reposcout query --tool rg`)
- symbol name search (`reposcout query --tool rg`)
- git history (`reposcout query --tool git_log`)
- bounded source read (`reposcout query --tool read`, or `reposcout pack`)

## 3. Pack First

When more than one source or range is needed, call `reposcout pack` before issuing
individual reads, rather than reading each range separately. See
[`pack_first_policy.md`](pack_first_policy.md) for the full six-point policy this
summarizes.

## 4. Re-read by Exception

Do not re-read a path/range/hash already returned by a Pack. Re-reading is permitted only
when:

- the Pack does not cover the needed range,
- the source has changed since the Pack was built,
- Evidence is contradictory, or
- a final decision requires close reading of a specific, already-narrowed range.

## 5. Search Intent vs Search Execution

Claude decides: what to investigate, which relation to follow next, whether the
premise/problem framing itself is sound, and what the Evidence means.

RepoScout decides none of that. It only provides: the repository's file universe,
deterministic search, bounded reads, git history, Pack, and evidence with a traceable
source location.

## 6. Explicit Semantic Exploration

RepoScout returning `UNRESOLVED` is not an invitation to fall back to an LLM automatically
-- RepoScout itself never does this (see Architecture Principle in the main README). If
semantic exploration is actually needed, Claude decides that explicitly and requests it
explicitly (`--tool ornith`), rather than treating "no deterministic tool matched" as
implicit permission.

## 7. Stop When Sufficient

Check `InvestigationContract.stop_conditions` (or the plan's own goal) once the required
Evidence is in hand, and stop. Do not keep exploring "just in case" once the questions the
investigation was for are answered.

## 8. UNKNOWN Preservation

Do not fill in what could not be confirmed. A query that came back `UNRESOLVED` or `ERROR`
is a fact worth keeping as-is (see `EvidenceContract.unknown`), not a gap to paper over with
an inferred answer.

---

## Commands Claude can call directly (via the Bash tool)

All examples assume `cwd` is this project (so `uv run reposcout` resolves) and
`--root <target-repo>` points at whatever repository is actually under investigation.

### `reposcout skeleton`

**For:** learning the file universe before referencing any path (Skeleton First).
**When:** at the start of an investigation, or whenever `target_hints` of kind `path` need
verifying.
**Returns:** one tracked (or, with `--scope workspace`, tracked + untracked-not-ignored)
path per line under `src` and `tests/unit`.

```bash smoketest
uv run reposcout skeleton --root <target-repo>
```

### `reposcout query`

**For:** a single deterministic lookup -- one `rg` / `read` / `git_log` call -- when a full
multi-query plan isn't needed.
**When:** answering one narrow, already-well-specified question.
**Returns:** one `EvidenceResult` (status, executor, raw evidence, source locations) as JSON.

```bash smoketest
uv run reposcout query --root <target-repo> --id Q1 --tool git_log
```

### `reposcout investigate`

**For:** running a multi-query `InvestigationPlan` in one pass and getting both raw
(`evidence.md`) and structured (`evidence-contract.json`) output.
**When:** the investigation needs more than one query, or a caller wants the deterministic
`EvidenceContract` (see [README](../README.md#evidence-contract)) rather than assembling one
by hand from individual `query` calls.
**Returns:** exit 0 if every query reached `PASS`; writes `plan.yaml`, per-query JSON,
`evidence.md`, and `evidence-contract.json` under the run directory (or `.reposcout/runs/`).

```bash smoketest
mkdir -p /tmp/reposcout-usage-policy-plan && cat > /tmp/reposcout-usage-policy-plan/plan.yaml <<'PLAN'
goal: smoke test
queries:
  - id: Q1
    tool: git_log
PLAN
uv run reposcout investigate /tmp/reposcout-usage-policy-plan/plan.yaml --root <target-repo> --output /tmp/reposcout-usage-policy-plan/run
```

### `reposcout pack`

**For:** merging/deduplicating several source ranges into one deterministic response
(Pack First).
**When:** more than one range across one or more files is needed before reasoning about
them.
**Returns:** `EvidencePack` JSON: merged `PackedSource` entries (path, range, content, hash)
plus `PackMetrics`.

```bash smoketest
mkdir -p /tmp/reposcout-usage-policy-pack && cat > /tmp/reposcout-usage-policy-pack/request.yaml <<'PACK'
ranges:
  - path: src/reposcout/models.py
    start_line: 1
    end_line: 5
PACK
uv run reposcout pack /tmp/reposcout-usage-policy-pack/request.yaml --root <target-repo>
```

---

## Investigation Trace

`investigate` accepts `--trace-out` and `--investigation-id`. Trace stays opt-in -- nothing
changes about default behavior if these are omitted. When an investigation should be
observable later (comparing exploration paths, joining with Claude-side token/cost
telemetry, or an external acceptance result), pass a caller-generated ID through so all
three can be joined on it later:

```bash smoketest
mkdir -p /tmp/reposcout-usage-policy-trace && cat > /tmp/reposcout-usage-policy-trace/plan.yaml <<'PLAN'
goal: traced smoke test
queries:
  - id: Q1
    tool: git_log
PLAN
uv run reposcout investigate /tmp/reposcout-usage-policy-trace/plan.yaml \
  --root <target-repo> \
  --output /tmp/reposcout-usage-policy-trace/run \
  --trace-out /tmp/reposcout-usage-policy-trace/trace.jsonl \
  --investigation-id claude-session-example
```

RepoScout does not generate or require its own ID scheme -- pass whatever ID the calling
session already uses (a Claude session ID, a task ID, anything unique to one investigation)
and RepoScout preserves it rather than substituting its own.
