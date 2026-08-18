# Evidence Contract / Investigation Trace Design

## Goal

Close RepoScout 1.0 with two deterministic observability contracts:

1. M7 exposes query evidence and source metadata without semantic interpretation.
2. M8 records the investigation execution path as optional JSONL trace data.

The existing raw evidence artifacts remain backward compatible.

## Architecture

`InvestigationPlan` is executed by the existing deterministic `QueryRunner`. Each
`EvidenceResult` remains the executor boundary result. `EvidenceWriter` builds an
`EvidenceContract` from the plan and results, preserving raw evidence text,
status, errors, and source metadata. `InvestigationRunner` optionally emits
`InvestigationStep` records while it executes queries and writes the contract.

No model, Ornith, AST, LSP, MCP, semantic classifier, rule generator, or rule
application is introduced.

## M7 Contract

`SourceLocation` contains `path`, inclusive `start_line` and `end_line`, and
optional `content_hash`. Locations are deduplicated by all fields and retain
first-observed stable order. `QueryEvidence` contains query identity, question,
executor, status, raw evidence, and locations. `UnknownEvidence` records
`UNRESOLVED` or `ERROR` with its query id and reason. `EvidenceContract` contains
goal, query evidence, deduplicated locations, and unknown entries.

Contract serialization uses Pydantic JSON round-tripping. `EvidenceWriter` keeps
`evidence.md`, per-query JSON, and adds `evidence-contract.json`.

## M8 Trace

`InvestigationTrace` contains a trace version, caller-preserved investigation
id, timestamps, ordered steps, and optional contract hash, repository commit,
and scope mode only when available. Each `InvestigationStep` records a closed
`TraceAction` (`skeleton`, `search`, `read`, `git_log`, `pack`, `unresolved`,
`error`, or `stop`), executor/status, query and target metadata, result count,
timing, byte counters, and source locations. Query steps are emitted in plan
order; pack and stop steps are emitted at their actual deterministic boundaries.

Trace output is opt-in through `investigate --trace-out PATH` and optional
`--investigation-id ID`. JSONL stores one trace envelope per line: one trace
header followed by one step per record. Source bodies are never copied into
trace records; the contract remains their source of truth. `.reposcout/` is
already ignored.

## Metrics and Boundaries

Trace metrics are deterministic from step fields: search/read/pack counts,
unique and repeated paths, unresolved/error counts, tool calls, elapsed time,
requested/packed bytes, eliminated bytes, and pack characters. No semantic
coverage, token cost, hidden reasoning, raw secrets, candidate rules, or
automatic policy changes are recorded.

## Testing and Quality

M7 tests cover status/executor preservation, raw evidence preservation,
location deduplication/order/hash, unknown statuses, partial contracts, and
JSON round-trip. M8 tests cover opt-in compatibility, deterministic sequence,
identity propagation, source metadata, pack metrics, unknown/error steps,
non-negative elapsed time, JSONL round-trip, no source duplication, and a CLI
integration path. The full repository quality gates remain pytest, ruff check,
ruff format check, and mypy.

## Future

A future `reposcout trace report` or external analyzer may compare repeated
exploration paths and join external evaluator outcomes by investigation id.
Frequent low-cost paths may become Rule Candidates, but human approval is
required before any policy, workflow, or tool promotion. This milestone does
not implement that analyzer or automatic learning/application.
