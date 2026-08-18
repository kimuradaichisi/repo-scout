## Coding Rules

These rules apply to all production code and experiment code unless explicitly
waived for generated data or static fixtures.

### Size Limits

- Maximum 300 lines per source file.
- Maximum 30 lines per function or method.
- Maximum 5 parameters per function or method.
- Cyclomatic complexity should remain <= 5 where practical.
- Do not increase the size of an already-oversized file by adding another
  responsibility. Extract the responsibility first.

The limits are guardrails for responsibility and reasoning locality, not goals.
Do not split code mechanically just to satisfy a line count if doing so would
make related behavior harder to understand.

### Responsibility

- One module should have one clear reason to change.
- Keep orchestration separate from execution, measurement, formatting, and
  persistence.
- Do not create God classes, God functions, or experiment scripts that own the
  entire workflow.
- Prefer small cohesive modules over large files with internal sections.
- Do not introduce abstractions only to reduce line count.
- Apply YAGNI: add only abstractions required by the current experiment or
  production behavior.

### Experiment Code

Experiment code is production-quality measurement code and must follow the same
quality standards as `src/`.

In particular:

- Experiment orchestration, prompt construction, metric collection,
  aggregation, reporting, snapshot preparation, and variant execution should
  be separate responsibilities.
- Adding a new experiment variant must not result in copying an entire previous
  runner implementation.
- Shared behavior between B1/B2/B3 variants should be extracted only when the
  behavior is genuinely identical.
- Experimental variants must remain independently identifiable so that changing
  one variant does not silently change historical baselines.
- Never modify stored baseline results to make a new experiment pass.
- Measurement fixes must be distinguishable from experiment behavior changes.

### Architecture

Dependency direction:

    Domain / Models
          ↓
    Application / Orchestration
          ↓
    Infrastructure / Executors / CLI

- Deterministic repository operations belong in executors or infrastructure.
- LLM-specific orchestration must not leak into deterministic executors.
- RepoScout must not use an LLM where a deterministic command can provide the
  required fact.
- Evidence collection and semantic judgment are separate responsibilities.
- Raw evidence must remain traceable to its source location.

### LLM / Agent Design

Use expensive reasoning only where semantic judgment is required.

Prefer:

    Reason → deterministic execution → compressed evidence → Reason

over:

    Reason → command → Reason → command → Reason

- Do not add an LLM call when deterministic code can produce the same result.
- Do not add an LLM synthesis step unless measurement shows that it improves
  quality enough to justify its cost.
- Preserve evidence instead of replacing it with unsupported summaries.
- UNKNOWN is preferable to inference without evidence.

### Python

- Python code must be type annotated.
- Avoid `Any` unless integration with an untyped external API makes it
  unavoidable.
- Prefer immutable values and explicit data models.
- External dependencies and nondeterministic behavior must be injected behind
  clear boundaries when testing requires substitution.
- Catch errors at boundaries; do not hide programming errors inside broad
  exception handlers.

### Quality Gates

Before declaring an implementation complete, run:

1. `uv run pytest -q`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run mypy src`
5. Verify the 300 / 30 / 5 limits for changed code.

Do not report completion while a quality gate is failing.

### Refactoring Rule

When a requested change would make a file exceed the limits or mix a new
responsibility into an existing module:

1. identify the responsibility being added,
2. extract that responsibility into an appropriately named module,
3. preserve existing behavior with tests,
4. then implement the requested change.

Do not perform unrelated cleanup or repository-wide refactoring.