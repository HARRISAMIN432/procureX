from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.extractions import (
    ExtractedFieldStatus,
    ExtractionStatus,
    ReviewAction,
)


def normalized_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value cannot be blank")
    return stripped


class BoundingBox(BaseModel):
    x: Decimal = Field(ge=0, max_digits=12, decimal_places=4)
    y: Decimal = Field(ge=0, max_digits=12, decimal_places=4)
    width: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    height: Decimal = Field(gt=0, max_digits=12, decimal_places=4)


class EvidenceAnchorWrite(BaseModel):
    page_number: int = Field(gt=0)
    quoted_text: str | None = Field(default=None, max_length=5000)
    bounding_box: BoundingBox | None = None
    cell_range: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_locator(self) -> "EvidenceAnchorWrite":
        if self.quoted_text is not None:
            self.quoted_text = normalized_text(self.quoted_text)
        if self.cell_range is not None:
            self.cell_range = normalized_text(self.cell_range)
        if self.quoted_text is None and self.bounding_box is None and self.cell_range is None:
            raise ValueError("Evidence anchor requires text, bounding_box, or cell_range")
        return self


class ExtractedFieldWrite(BaseModel):
    field_key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z][a-z0-9_.]*$")
    label: str = Field(min_length=1, max_length=250)
    data_type: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    raw_value: Any | None = None
    normalized_value: Any | None = None
    status: ExtractedFieldStatus
    is_critical: bool = False
    confidence: Decimal | None = Field(default=None, ge=0, le=1, max_digits=5, decimal_places=4)
    anchors: list[EvidenceAnchorWrite] = Field(default_factory=list, max_length=50)

    _label = field_validator("label")(normalized_text)

    @model_validator(mode="after")
    def validate_proposal(self) -> "ExtractedFieldWrite":
        allowed = {
            ExtractedFieldStatus.PROPOSED,
            ExtractedFieldStatus.MISSING,
            ExtractedFieldStatus.AMBIGUOUS,
            ExtractedFieldStatus.CONFLICTING,
        }
        if self.status not in allowed:
            raise ValueError("Extraction output cannot pre-verify or reject a field")
        if self.status is ExtractedFieldStatus.MISSING:
            if self.raw_value is not None or self.normalized_value is not None:
                raise ValueError("Missing fields cannot contain values")
            if self.anchors:
                raise ValueError("Missing fields cannot claim supporting evidence")
        elif not self.anchors:
            raise ValueError("Extracted values require at least one evidence anchor")
        return self


class ExtractionResultCreate(BaseModel):
    parse_id: UUID
    result_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    schema_name: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.]*$")
    schema_version: str = Field(min_length=1, max_length=80)
    fields: list[ExtractedFieldWrite] = Field(min_length=1, max_length=1000)

    @field_validator("fields")
    @classmethod
    def unique_field_keys(cls, fields: list[ExtractedFieldWrite]) -> list[ExtractedFieldWrite]:
        keys = [field.field_key for field in fields]
        if len(keys) != len(set(keys)):
            raise ValueError("field_key values must be unique")
        return fields


class FieldReviewCreate(BaseModel):
    expected_revision: int = Field(gt=0)
    action: ReviewAction
    normalized_value: Any | None = None
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        stripped = normalized_text(value)
        if len(stripped) < 2:
            raise ValueError("Reason must contain at least 2 characters")
        return stripped

    @model_validator(mode="after")
    def correction_requires_value(self) -> "FieldReviewCreate":
        if self.action is ReviewAction.CORRECT and self.normalized_value is None:
            raise ValueError("A corrected field requires normalized_value")
        if self.action is not ReviewAction.CORRECT and self.normalized_value is not None:
            raise ValueError("Only a correction may replace normalized_value")
        return self


class ExtractionFinalize(BaseModel):
    expected_revision: int = Field(gt=0)


class EvidenceAnchorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_id: UUID
    quoted_text: str | None
    bounding_box: dict[str, Any] | None
    cell_range: str | None


class FieldReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: ReviewAction
    previous_status: str
    previous_value: Any | None
    reviewed_status: str
    reviewed_value: Any | None
    reason: str
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime


class ExtractedFieldRead(BaseModel):
    id: UUID
    field_key: str
    label: str
    data_type: str
    raw_value: Any | None
    normalized_value: Any | None
    status: ExtractedFieldStatus
    is_critical: bool
    confidence: Decimal | None
    anchors: list[EvidenceAnchorRead]
    reviews: list[FieldReviewRead]


class ExtractionRead(BaseModel):
    id: UUID
    document_version_id: UUID
    parse_id: UUID
    analysis_run_id: UUID
    version: int
    revision: int
    result_key: str
    schema_name: str
    schema_version: str
    status: ExtractionStatus
    source_digest: str
    content_digest: str
    created_at: datetime
    completed_at: datetime | None
    fields: list[ExtractedFieldRead]
