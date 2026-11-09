from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Constraints(StrictModel):
    scenic_spot: str | None = None
    duration: str | None = None
    days: int | None = Field(default=None, ge=1, le=30)
    travelers: list[str] = Field(default_factory=list, max_length=10)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    must_visit: list[str] = Field(default_factory=list, max_length=15)
    avoid: list[str] = Field(default_factory=list, max_length=15)
    weather: str | None = None


class AdviceChoice(StrictModel):
    pair_id: str
    user_evidence: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=500)


class AdviceVerdict(StrictModel):
    pair_id: str
    verdict: Literal["matched", "unknown", "contradicted"]
    reason: str


class AdviceAudit(StrictModel):
    decisions: list[AdviceVerdict]


class Proposal(StrictModel):
    status: Literal["ready", "clarification", "no_match"]
    message: str = Field(min_length=1, max_length=1200)
    route_id: str | None = None
    orders: list[int] = Field(default_factory=list, max_length=80)
    advice: list[AdviceChoice] = Field(default_factory=list, max_length=8)
    rationale: str = Field(default="", max_length=1000)


class PlanRequest(StrictModel):
    message: str = Field(min_length=1, max_length=3000)
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class RouteSearch(StrictModel):
    scenic_spot: str


class RouteDetails(StrictModel):
    route_id: str = Field(min_length=1, max_length=200)


class AdviceSearch(StrictModel):
    scenic_spot: str


class SourceRequest(StrictModel):
    doc_id: str = Field(min_length=1, max_length=200)
