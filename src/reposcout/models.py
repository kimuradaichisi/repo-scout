from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator  # pyright: ignore[reportMissingImports]


class QueryTool(StrEnum):
    RG = "rg"
    READ = "read"
    GIT_LOG = "git_log"
    ORNITH = "ornith"


class InvestigationQuery(BaseModel):
    id: str = Field(min_length=1)
    instruction: str | None = None
    tool: QueryTool | None = None

    pattern: str | None = None
    paths: list[str] = Field(default_factory=list)

    file: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)

    git_args: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_query(self) -> "InvestigationQuery":
        if self.tool is None and not self.instruction:
            raise ValueError("instruction is required when tool is omitted")
        if self.tool == QueryTool.RG and not self.pattern:
            raise ValueError("pattern is required for rg queries")
        if self.tool == QueryTool.READ and not self.file:
            raise ValueError("file is required for read queries")
        if self.start_line and self.end_line and self.start_line > self.end_line:
            raise ValueError("start_line must be <= end_line")
        return self


class InvestigationPlan(BaseModel):
    goal: str = Field(min_length=1)
    queries: list[InvestigationQuery] = Field(min_length=1)


class TargetHint(BaseModel):
    """A caller-typed starting point for exploration -- not a verified fact.

    kind is chosen by the caller. RepoScout does not infer path/symbol-ness
    from the text of value.
    """

    kind: Literal["path", "symbol", "literal"]
    value: str = Field(min_length=1)


class InvestigationContract(BaseModel):
    """What the caller wants investigated -- not what was found.

    known_facts are caller-confirmed; RepoScout does not re-derive them.
    target_hints are unconfirmed starting points, not facts.
    """

    goal: str = Field(min_length=1)
    questions: list[str] = Field(min_length=1)
    known_facts: list[str] = Field(default_factory=list)
    target_hints: list[TargetHint] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(min_length=1)


class EvidenceResult(BaseModel):
    query_id: str
    status: Literal["PASS", "ERROR", "UNRESOLVED"]
    executor: str
    evidence: str = ""
    error: str | None = None
    source_locations: list["SourceLocation"] = Field(default_factory=list)
    result_count: int | None = Field(default=None, ge=0)
    input_bytes: int | None = Field(default=None, ge=0)
    output_bytes: int | None = Field(default=None, ge=0)


class SourceLocation(BaseModel):
    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "SourceLocation":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class QueryEvidence(BaseModel):
    query_id: str
    question: str
    executor: str
    status: Literal["PASS", "ERROR", "UNRESOLVED"]
    evidence: str
    source_locations: list[SourceLocation] = Field(default_factory=list)


class UnknownEvidence(BaseModel):
    query_id: str
    reason: str
    status: Literal["ERROR", "UNRESOLVED"]


class EvidenceContract(BaseModel):
    goal: str
    query_evidence: list[QueryEvidence]
    source_locations: list[SourceLocation] = Field(default_factory=list)
    unknown: list[UnknownEvidence] = Field(default_factory=list)


class SourceRange(BaseModel):
    """A requested source excerpt. 1-origin, inclusive on both ends."""

    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "SourceRange":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class PackedSource(BaseModel):
    path: str
    start_line: int
    end_line: int
    content: str
    sha256: str


class PackMetrics(BaseModel):
    requested_ranges: int
    packed_ranges: int
    requested_source_bytes: int
    packed_source_bytes: int
    duplicate_or_overlap_bytes_eliminated: int
    unique_paths: int
    pack_chars: int


TraceAction = Literal[
    "skeleton",
    "search",
    "read",
    "git_log",
    "pack",
    "unresolved",
    "error",
    "stop",
]


class InvestigationStep(BaseModel):
    sequence: int = Field(ge=1)
    action: TraceAction
    executor: str
    status: Literal["PASS", "ERROR", "UNRESOLVED"]
    query_id: str | None = None
    target_kind: str | None = None
    target_value: str | None = None
    result_count: int | None = Field(default=None, ge=0)
    elapsed_ms: int | None = Field(default=None, ge=0)
    input_bytes: int | None = Field(default=None, ge=0)
    output_bytes: int | None = Field(default=None, ge=0)
    source_locations: list[SourceLocation] = Field(default_factory=list)
    pack_metrics: PackMetrics | None = None


class EvidencePack(BaseModel):
    sources: list[PackedSource]
    metrics: PackMetrics


class InvestigationTrace(BaseModel):
    trace_version: str = "1"
    investigation_id: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime | None = None
    steps: list[InvestigationStep] = Field(default_factory=list)
    contract_hash: str | None = None
    repository_commit: str | None = None
    scope_mode: str | None = None

    def add_step(
        self, action: TraceAction, executor: str, status: str, **fields: object
    ) -> InvestigationStep:
        data: dict[str, object] = {
            "sequence": len(self.steps) + 1,
            "action": action,
            "executor": executor,
            "status": status,
            **fields,
        }
        step = InvestigationStep.model_validate(data)
        self.steps.append(step)
        return step


class TraceMetrics(BaseModel):
    search_count: int = 0
    read_count: int = 0
    pack_count: int = 0
    unique_paths: int = 0
    repeated_paths: int = 0
    unresolved_count: int = 0
    error_count: int = 0
    tool_calls: int = 0
    elapsed_ms: int = 0
    requested_source_bytes: int = 0
    packed_source_bytes: int = 0
    duplicate_or_overlap_bytes_eliminated: int = 0
    pack_chars: int = 0


class PackRequest(BaseModel):
    ranges: list[SourceRange] = Field(min_length=1)


class RunContext(BaseModel):
    root: Path
    run_dir: Path
