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
    status: Literal["PASS", "ERROR"]
    executor: str
    evidence: str = ""
    error: str | None = None


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


class EvidencePack(BaseModel):
    sources: list[PackedSource]
    metrics: PackMetrics


class PackRequest(BaseModel):
    ranges: list[SourceRange] = Field(min_length=1)


class RunContext(BaseModel):
    root: Path
    run_dir: Path
