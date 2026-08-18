RepoScout

RepoScout is a local repository investigation runner that lets a caller such as Claude Code, another coding agent, or a human collect repository evidence through deterministic tools and return it in a compact, source-grounded form.

Strong Model for Search Intent / Deterministic Tool for Search Execution

RepoScout does not replace a strong model's reasoning. Its role is to offload repository discovery, exact search, bounded reads, Git inspection, evidence packing, and trace collection so that the model can spend its reasoning budget on deciding what to investigate and what the evidence means.

Deterministic execution is the default and requires no LLM.

A query either:

explicitly selects a deterministic tool (rg / read / git_log),

explicitly selects ornith, or

returns UNRESOLVED.

RepoScout never guesses that an ambiguous query is "probably for Ornith".

Status

RepoScout 1.0

Product Acceptance completed with model call count 0.

Validated task classes:

Symbol / Reference

Behavior Localization

Change Scope

Acceptance results:

coverage: 1.0 for all three task classes

fictional paths: 0

repository leaks: 0

explicit UNRESOLVED preservation: confirmed

Ornith calls on deterministic acceptance path: 0

Investigation Trace investigation_id preservation: confirmed

Goal

Reduce repository-discovery work performed by coding agents.

RepoScout aims to move work that can be determined mechanically out of the model's reasoning loop.

Reason
  ↓
Determinize
  ↓
Execute
  ↓
Compress Evidence
  ↓
Reason

Typical split:

Claude / Human / other caller
  ├─ decide what should be investigated
  ├─ decide what relationships matter
  ├─ validate premises / problem framing
  └─ perform semantic judgment
                ↓
         Investigation Plan
                ↓
             RepoScout
  ├─ repository file scope
  ├─ skeleton
  ├─ ripgrep
  ├─ bounded read
  ├─ git log
  ├─ evidence pack
  └─ investigation trace
                ↓
        Evidence Contract
                ↓
Claude / Human / other caller
  └─ interpret the evidence

Core Principles

1. Skeleton First

Before repeatedly listing directories or opening files, establish the repository file universe.

2. Deterministic Search First

Use deterministic tools for facts that can be established mechanically:

path existence

literal search

symbol-name search

bounded source reads

Git history

3. Pack First

When multiple source ranges are needed, merge and deduplicate them before repeatedly reading overlapping ranges.

4. Re-read by Exception

Do not re-read a range that is already packed unless:

the needed range is missing,

the source changed,

the evidence conflicts,

or final local precision requires a focused read.

5. Search Intent and Search Execution Are Different Responsibilities

The caller decides what should be investigated.

RepoScout executes the investigation deterministically.

6. Semantic Exploration Is Explicit

Ornith is never selected as an implicit fallback.

7. Stop When Evidence Is Sufficient

Do not continue exploration "just in case" after the caller's stop conditions have been satisfied.

8. Preserve UNKNOWN

If a question cannot be resolved, preserve that state as UNRESOLVED rather than inventing an answer.

v1.0 Scope

Included:

repository skeleton

tracked/workspace file scope

rg text search

bounded file reads

git log

explicit Ornith query execution

multi-query Investigation Plans

deterministic Evidence Contract

source locations for traceable evidence where the executor can confirm them

Evidence Pack with range merge/deduplication

incremental JSONL Investigation Trace

Claude / RepoScout Bash-tool usage policy

Not included:

MCP server

LSP

AST graph

automatic semantic planner

automatic model routing

automatic Rule Candidate generation

automatic Rule/Policy promotion

long-term agent memory

RAG/vector database

multi-repository product validation

include-ignored file-scope mode

human-friendly reposcout trace report

Requirements

Python 3.12+

uv

rg

git

For explicit Ornith queries only:

OpenCode available on PATH

Ornith/OpenCode configuration matching your local environment

Deterministic usage does not require Ornith or any LLM.

Setup

uv sync --extra dev

Run the quality gates:

uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src

Install RepoScout Locally

The steps above (`uv sync`, `uv run reposcout ...`) only work from inside this
repository's own checkout and virtual environment. To call `reposcout`
directly from another repository, install it as a standalone uv tool instead:

uv tool install --editable /path/to/repo-scout

This resolves RepoScout into its own isolated environment under uv's tool
directory (`uv tool dir`) and puts a `reposcout` executable on `PATH`
(typically `~/.local/bin/reposcout`) that does not depend on this
repository's `.venv`. `--editable` means edits to this checkout take effect
immediately, with no reinstall step.

Verify it from outside this repository:

cd /
reposcout --help

Use RepoScout From Another Repository

Once installed, run any command with `--root` pointing at the repository
under investigation, from anywhere on the machine:

reposcout skeleton --root /path/to/target-repo
reposcout query --root /path/to/target-repo --id Q1 --tool git_log
reposcout investigate examples/investigation.yaml --root /path/to/target-repo

Upgrade / Reinstall The Local Checkout

Because `--editable` installs point at this checkout's source directly, most
code changes need no reinstall. If `pyproject.toml` changes (dependencies,
the entry point) or the tool install is otherwise out of sync, reinstall:

uv tool install --editable --force /path/to/repo-scout

Uninstall

uv tool uninstall reposcout

Quick Start

1. Inspect the Repository Skeleton

Tracked files only:

uv run reposcout skeleton --root ../target-repo

Include untracked but non-ignored workspace files:

uv run reposcout skeleton \
  --root ../target-repo \
  --scope workspace

Use Skeleton before broad repository browsing.

2. Run a Single Deterministic Query

Example: search for a symbol or literal.

uv run reposcout query \
  --root ../target-repo \
  --id Q1 \
  --tool rg \
  --pattern ExecuteContract \
  --path tools \
  --path tests

This does not invoke an LLM.

3. Run a Single Explicit Ornith Query

Ornith is opt-in.

uv run reposcout query \
  --root ../target-repo \
  --id Q1 \
  --tool ornith \
  --instruction "ExecuteContract の参照箇所を調査し、根拠を返せ"

Without --tool ornith, an instruction-only query is not automatically routed to Ornith.

The default Ornith command is configured in:

src/reposcout/ornith/client.py

Adjust it to match your OpenCode agent/model setup.

Investigation Plan

reposcout investigate accepts an InvestigationPlan YAML file.

Minimum structure:

goal: Investigate ExecuteContract impact

queries:
  - id: Q1
    tool: rg
    pattern: ExecuteContract
    paths:
      - tools
      - tests

A fuller example:

goal: ExecuteContract 変更の影響範囲を調査する

queries:
  - id: Q1
    tool: rg
    pattern: ExecuteContract
    paths:
      - tools
      - tests

  - id: Q2
    tool: read
    file: tools/dev_agent/application/execute_contract.py
    start_line: 1
    end_line: 220

  - id: Q3
    tool: git_log
    git_args:
      - --oneline
      - --
      - tools/dev_agent/application/execute_contract.py

  - id: Q4
    tool: ornith
    instruction: >
      ExecuteContract を利用するテストについて、
      deterministic evidenceだけでは判断できない関係を調査する。

Run:

uv run reposcout investigate \
  --root ../target-repo \
  examples/investigation.yaml

You may also pass the plan first:

uv run reposcout investigate \
  examples/investigation.yaml \
  --root ../target-repo

Both forms are equivalent because plan is the required positional argument.

Query Schema

rg

- id: Q1
  tool: rg
  pattern: RipgrepExecutor
  paths:
    - src
    - tests

Required:

id

tool: rg

pattern

Optional:

paths

RepoScout records one SourceLocation per confirmed match line.

Context lines are not turned into source locations unless they are themselves confirmed matches.

read

- id: Q2
  tool: read
  file: src/reposcout/runner.py
  start_line: 1
  end_line: 100

Required:

id

tool: read

file

Optional:

start_line

end_line

The resulting SourceLocation reflects the actual range read.

If EOF is reached before the requested end_line, RepoScout records the actual returned range rather than inventing lines that do not exist.

git_log

- id: Q3
  tool: git_log
  git_args:
    - --oneline
    - --
    - src/reposcout/runner.py

Git log evidence is preserved as raw evidence.

source_locations is intentionally empty because a commit record is not a source-file line range.

RepoScout does not invent path:start_line:end_line metadata for Git history.

ornith

- id: Q4
  tool: ornith
  instruction: >
    Investigate the semantic relationship that deterministic evidence
    alone cannot resolve.

Ornith is called only when tool: ornith is explicit.

Tool Omitted

This is valid only when instruction is present:

- id: Q5
  instruction: Find the consumer relationship.

RepoScout does not infer a tool from this instruction.

The query is preserved as UNRESOLVED.

This is intentional.

InvestigationContract vs InvestigationPlan

RepoScout contains two different models with different responsibilities.

InvestigationContract

Conceptual caller-side investigation intent:

goal
questions
known_facts
target_hints
constraints
stop_conditions

Example shape:

goal: Determine change impact

questions:
  - Where is RipgrepExecutor used?
  - Which component consumes it?

known_facts: []

target_hints:
  - kind: symbol
    value: RipgrepExecutor

constraints:
  - Do not infer missing paths.

stop_conditions:
  - Target definition and direct consumers are supported by evidence.

InvestigationPlan

Concrete executable queries:

goal
queries

Example:

goal: Determine change impact

queries:
  - id: Q1
    tool: rg
    pattern: RipgrepExecutor
    paths:
      - src
      - tests

Important Boundary

The current reposcout investigate CLI accepts InvestigationPlan, not InvestigationContract.

RepoScout 1.0 does not automatically compile:

InvestigationContract
        ↓
InvestigationPlan

That translation is currently the responsibility of the caller such as Claude, another planner, or a human.

This boundary is intentional: semantic judgment about what should be searched stays outside the deterministic execution engine.

Investigation Output

A normal investigation produces a run directory containing artifacts similar to:

.reposcout/
└── runs/
    └── <run-id>/
        ├── plan.yaml
        ├── Q1.json
        ├── Q2.json
        ├── ...
        ├── evidence.md
        └── evidence-contract.json

evidence.md is a human-readable evidence view.

evidence-contract.json is the deterministic machine-readable output intended for downstream reasoning.

Evidence Contract

evidence-contract.json contains:

goal
query_evidence
source_locations
unknown

Each QueryEvidence contains:

query_id
question
executor
status
evidence
source_locations

evidence is preserved as raw executor output.

RepoScout does not:

summarize it semantically,

infer FACTS,

infer RELATIONS,

decide the final meaning,

or fabricate missing evidence.

Those are caller-side responsibilities.

SourceLocation

A SourceLocation contains:

path
start_line
end_line
content_hash

content_hash is optional.

Behavior differs by executor.

rg

One source location per confirmed match line.

start_line == end_line

read

One source location for the actual range returned.

The content hash corresponds to the returned content.

git_log

source_locations = []

A Git commit is not a source line range.

pack

One source location per PackedSource.

PackedSource.sha256 is preserved as content_hash.

UNKNOWN and ERROR

RepoScout keeps ERROR and UNRESOLVED distinct.

ERROR means an executor was selected and execution failed.

UNRESOLVED means RepoScout did not deterministically resolve the query.

Both are preserved in EvidenceContract.unknown.

RepoScout does not silently turn either case into a semantic conclusion.

Repository File Scope

RepositoryFileScope defines the deterministic file universe used by Skeleton and Pack.

Git's ignore semantics are the source of truth.

RepoScout does not hard-code exclusions such as node_modules or .venv; it relies on Git.

Available modes:

tracked-only — default

Equivalent in principle to:

git ls-files

Only tracked files are visible.

workspace

Equivalent in principle to:

git ls-files --cached --others --exclude-standard

Includes:

tracked files

untracked files not ignored by Git

Excludes Git-ignored files.

Example:

uv run reposcout skeleton \
  --root ../target-repo \
  --scope workspace

include-ignored is not implemented in v1.0.

Current v1.0 Limitation

The current file-scope implementation is optimized around the repository layouts used during RepoScout development and acceptance.

Multi-repository generalization is a Future item and should be validated before treating every repository layout as equally supported.

Evidence Pack — Pack First

reposcout pack merges and deduplicates requested source ranges before returning the source to a caller.

Example request:

ranges:
  - path: src/reposcout/evidence.py
    start_line: 1
    end_line: 20

  - path: src/reposcout/evidence.py
    start_line: 15
    end_line: 30

Run:

uv run reposcout pack \
  request.yaml \
  --root ../target-repo

Overlapping or contiguous ranges are merged deterministically.

The output contains PackedSource and PackMetrics.

PackMetrics contains:

requested_ranges
packed_ranges
requested_source_bytes
packed_source_bytes
duplicate_or_overlap_bytes_eliminated
unique_paths
pack_chars

No LLM is required.

See:

docs/pack_first_policy.md

Investigation Trace

Investigation Trace records observable execution metadata.

It is not chain-of-thought and does not contain hidden model reasoning.

Trace is intended for:

Observe
  ↓
Compare
  ↓
Rule Candidate
  ↓
Human Approval
  ↓
Policy / Workflow / Tool

RepoScout 1.0 records observation data only.

It does not automatically infer semantic coverage, generate rules, promote rules, or apply policies.

Enable Trace

Tracing is opt-in.

uv run reposcout investigate \
  examples/investigation.yaml \
  --root ../target-repo \
  --trace-out .reposcout/traces/investigation.jsonl \
  --investigation-id caller-provided-id

The same investigation_id is written across the trace so callers can later join:

Claude telemetry
+
RepoScout trace
+
token/cost telemetry
+
acceptance result

Trace Storage

Trace is JSONL.

Records are appended incrementally as the investigation runs:

header
step
step
...
stop
complete

A crash after one or more steps leaves a valid partial trace rather than losing the whole investigation history.

Source bodies are not duplicated in the trace.

The Evidence Contract remains the source of truth for evidence text.

Trace Actions

Examples:

skeleton
search
read
git_log
pack
semantic_explore
unresolved
error
stop

Important distinction:

action = search
executor = ripgrep

means deterministic search.

action = semantic_explore
executor = ornith

means explicit semantic exploration.

These are intentionally separate so future cost/rule analysis does not mix an LLM call with rg.

Inspect Trace

Raw:

cat .reposcout/traces/investigation.jsonl

Pretty-print with jq:

jq . .reposcout/traces/investigation.jsonl

Show only investigation steps:

jq -r '
  select(.sequence != null) |
  [.sequence, .action, .executor, .status, .query_id] |
  @tsv
' .reposcout/traces/investigation.jsonl

A human-friendly reposcout trace report command is not implemented in v1.0.

Claude / RepoScout Integration

RepoScout 1.0 uses a Bash-tool convention rather than MCP.

Claude
  ↓
Bash Tool
  ↓
RepoScout CLI
  ↓
Evidence Contract / Evidence Pack
  ↓
Claude

No dedicated RepoScout Agent is required.

No new LLM dependency is added to RepoScout.

See:

docs/claude_usage_policy.md

for the complete usage policy.

Recommended Claude Flow

1. Skeleton First

2. Claude decides the Search Intent

3. RepoScout executes deterministic queries

4. RepoScout returns Evidence Contract

5. Multiple required ranges are packed with Pack First

6. Claude performs semantic judgment

7. Re-read only by exception

8. Stop when evidence is sufficient

9. Preserve UNKNOWN

In other words:

Claude decides what to investigate. RepoScout performs the mechanical repository work.

Example: Investigate RepoScout Itself

Create a plan:

cat > /tmp/reposcout-plan.yaml <<'EOF'
goal: Investigate RipgrepExecutor implementation and references

queries:
  - id: Q1
    tool: rg
    pattern: RipgrepExecutor
    paths:
      - src
      - tests

  - id: Q2
    tool: read
    file: src/reposcout/executors/ripgrep.py
    start_line: 1
    end_line: 120

  - id: Q3
    tool: git_log
    git_args:
      - --oneline
      - --
      - src/reposcout/executors/ripgrep.py
EOF

Run with trace:

mkdir -p .reposcout/traces

uv run reposcout investigate \
  /tmp/reposcout-plan.yaml \
  --root . \
  --trace-out .reposcout/traces/ripgrep.jsonl \
  --investigation-id ripgrep-001

Inspect the trace:

jq . .reposcout/traces/ripgrep.jsonl

Inspect the generated Evidence Contract in the run output directory:

jq . .reposcout/runs/<run-id>/evidence-contract.json

Product Acceptance

RepoScout 1.0 was accepted using existing CP7 task classes without model calls.

Validated:

Task class

Coverage

Fictional paths

Repo leak

Result

Symbol / Reference

1.0

0

0

PASS

Behavior Localization

1.0

0

0

PASS

Change Scope

1.0

0

0

PASS

The acceptance path was:

Investigation Plan
  ↓
Deterministic RepoScout execution
  ↓
Evidence Contract
  ↓
Model-free evaluator

Additional acceptance properties:

source traceability confirmed

UNRESOLVED preserved

ERROR not hidden

Ornith calls: 0

Investigation Trace ID preserved

deterministic execution reproduced on repeated run

What RepoScout Does Not Guarantee

RepoScout guarantees deterministic execution only for the deterministic parts it owns.

It does not guarantee that:

a caller asked the right question,

a search pattern captured every semantic relationship,

source text alone is sufficient to infer behavior,

a final model interpretation is correct,

the current v1.0 repository-scope assumptions generalize to every repository.

Those remain caller, model, evaluator, or future-tool responsibilities.

Architecture Boundary

The most important boundary in RepoScout 1.0 is:

Semantic Judgment
      │
      │ caller responsibility
      ▼
Investigation Plan
      │
      │ deterministic execution
      ▼
RepoScout
      │
      ▼
Evidence Contract
      │
      │ caller responsibility
      ▼
Semantic Result

RepoScout intentionally does not turn raw evidence into semantic FACTS or RELATIONS.

A future caller may return a structured Semantic Result Contract, but that is outside RepoScout's deterministic evidence layer.

Future / Parking Lot

Potential future work:

reposcout trace report

frequent exploration paths

median tool-call counts

repeated searches / reads

unresolved hotspots

external evaluator joins

Rule Candidate Analyzer

propose efficient repeated exploration patterns

never auto-promote without human approval

Multi-repository validation

LSP-backed symbol queries

AST-backed structural queries

MCP adapter

include-ignored RepositoryFileScope mode

Evidence-budget / stop-condition enforcement improvements

Future work should preserve the core rule:

Do not make the model execute work that deterministic software can perform more cheaply, quickly, and reproducibly.

Summary

RepoScout 1.0 is not an autonomous repository agent.

It is a deterministic evidence engine designed to reduce repository-search reasoning performed by coding agents.

Caller decides what to investigate
        ↓
RepoScout executes deterministic repository work
        ↓
RepoScout returns traceable evidence
        ↓
Caller decides what the evidence means

The design goal is not to make the LLM deterministic.

The design goal is to place the non-deterministic LLM inside a more deterministic engineering process.