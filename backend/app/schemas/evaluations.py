from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.evaluations import EvaluationStatus, OfferEligibility, RequirementOutcome


class ScoringPolicy(BaseModel):
    price_weight: Decimal = Field(ge=0, le=1, max_digits=7, decimal_places=6)
    preferred_weight: Decimal = Field(ge=0, le=1, max_digits=7, decimal_places=6)

    @model_validator(mode="after")
    def weights_total_one(self) -> "ScoringPolicy":
        if self.price_weight + self.preferred_weight != Decimal("1"):
            raise ValueError("Scoring weights must total exactly 1")
        return self


class RequirementAssessmentWrite(BaseModel):
    requirement_id: UUID
    outcome: RequirementOutcome
    rationale: str = Field(min_length=2, max_length=5000)

    @field_validator("rationale")
    @classmethod
    def normalize_rationale(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Rationale must contain at least 2 characters")
        return value


class OfferAssessmentWrite(BaseModel):
    submission_id: UUID
    checks: list[RequirementAssessmentWrite] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_requirements(self) -> "OfferAssessmentWrite":
        requirement_ids = [check.requirement_id for check in self.checks]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("Each requirement may be assessed only once per offer")
        return self


class EvaluationCreate(BaseModel):
    expected_rfq_version: int = Field(gt=0)
    scoring_policy: ScoringPolicy
    offers: list[OfferAssessmentWrite] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_submissions(self) -> "EvaluationCreate":
        submission_ids = [offer.submission_id for offer in self.offers]
        if len(submission_ids) != len(set(submission_ids)):
            raise ValueError("Each submission may be evaluated only once")
        return self


class RequirementCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rfq_requirement_id: UUID
    outcome: RequirementOutcome
    is_mandatory: bool
    rationale: str


class OfferEvaluationRead(BaseModel):
    id: UUID
    submission_id: UUID
    supplier_id: UUID
    eligibility: OfferEligibility
    landed_cost: Decimal
    preferred_ratio: Decimal
    score: Decimal | None
    checks: list[RequirementCheckRead]


class EvaluationRead(BaseModel):
    id: UUID
    rfq_id: UUID
    version: int
    source_rfq_version: int
    publication_number: int
    currency: str
    status: EvaluationStatus
    scoring_policy: ScoringPolicy
    content_digest: str
    created_at: datetime
    offers: list[OfferEvaluationRead]
