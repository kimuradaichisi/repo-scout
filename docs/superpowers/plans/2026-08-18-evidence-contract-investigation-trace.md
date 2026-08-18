# Evidence Contract / Investigation Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic evidence contracts and opt-in investigation JSONL traces while preserving existing RepoScout behavior.

**Architecture:** Extend the existing Pydantic domain models with contract and trace records. Keep executor results and raw evidence artifacts intact; have `EvidenceWriter` build the M7 contract and `InvestigationRunner` optionally emit M8 records. CLI activation remains explicit with `--trace-out` and caller-supplied investigation IDs.

**Tech Stack:** Python, Pydantic, pytest, argparse, JSONL.

---

### Task 1: M7 contract models and builder

**Files:**
- Modify: `src/reposcout/models.py`
- Modify: `src/reposcout/evidence.py`
- Test: `tests/unit/test_evidence_contract.py`

- [ ] Write tests for successful query mapping, status/executor preservation, raw evidence preservation, source deduplication and stable order, unknown status preservation, packed hashes, partial contracts, and JSON round-trip.
- [ ] Run `uv run pytest tests/unit/test_evidence_contract.py -q` and confirm the new API fails before implementation.
- [ ] Add typed Pydantic models and deterministic builder logic with no semantic transformation.
- [ ] Run the focused test file and confirm it passes.
- [ ] Add `EvidenceWriter.write_contract` while retaining existing raw writers.
- [ ] Run `uv run pytest tests/unit/test_evidence.py tests/unit/test_evidence_contract.py -q`.

### Task 2: Integrate M7 contract into investigation execution

**Files:**
- Modify: `src/reposcout/runner.py`
- Test: `tests/unit/test_runner.py`

- [ ] Add a test asserting investigate execution writes the contract without changing result status or raw pack output.
- [ ] Run the focused test and confirm it fails because the contract is not written.
- [ ] Invoke `build_contract`/`write_contract` after query results are collected.
- [ ] Run the focused runner tests and the existing runner tests.

### Task 3: M8 trace domain and JSONL storage

**Files:**
- Create: `src/reposcout/trace.py`
- Modify: `src/reposcout/models.py`
- Test: `tests/unit/test_trace.py`

- [ ] Write tests for deterministic step sequence, shared investigation id, status/executor/query id/source metadata, non-negative elapsed values, pack metrics, and JSONL round-trip without source content.
- [ ] Run the focused test file and confirm it fails before implementation.
- [ ] Implement a small trace writer that writes one header and one step per JSONL line, with stable JSON field order and no source body.
- [ ] Run the focused trace tests and confirm they pass.

### Task 4: Instrument the investigation runner

**Files:**
- Modify: `src/reposcout/runner.py`
- Test: `tests/unit/test_trace.py`

- [ ] Add tests for trace-disabled compatibility, trace-enabled query/pack/unknown/error records, and caller ID preservation.
- [ ] Run them red.
- [ ] Add optional trace parameters to `InvestigationRunner.execute` and emit records at query and pack boundaries using `perf_counter`.
- [ ] Derive only deterministic byte/count/path metrics from existing result and pack metadata.
- [ ] Run the focused trace and runner tests.

### Task 5: Add CLI activation and documentation

**Files:**
- Modify: `src/reposcout/cli.py`
- Modify: `README.md`
- Test: `tests/integration/test_trace_cli.py`

- [ ] Add a CLI integration test invoking `investigate --trace-out` with a deterministic plan and checking JSONL records and investigation ID.
- [ ] Run the integration test red.
- [ ] Add `--trace-out` and `--investigation-id`, preserving default output and return codes.
- [ ] Document Observe -> Compare -> Candidate -> Human Approve -> Policy / Workflow / Tool, the non-learning boundary, activation, schema, and future analyzer parking lot.
- [ ] Run the focused CLI integration test.

### Task 6: Full quality gates and commit

**Files:**
- Modify: files from Tasks 1-5 only.

- [ ] Run `uv run pytest -q`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run ruff format --check .`.
- [ ] Run `uv run mypy src`.
- [ ] Check changed source files and functions against the 300 / 30 / 5 limits.
- [ ] Confirm no model, Ornith, Claude, AST, LSP, MCP, or experiment calls were added.
- [ ] Commit the implementation with a focused message.
