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


class EvidenceResult(BaseModel):
    query_id: str
    status: Literal["PASS", "ERROR"]
    executor: str
    evidence: str = ""
    error: str | None = None


class RunContext(BaseModel):
    root: Path
    run_dir: Path
