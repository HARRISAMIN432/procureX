from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.documents import (
    AssetStatus,
    DocumentStatus,
    DocumentVersionStatus,
    ParseKind,
    ParseStatus,
    ScanStatus,
)

SUPPORTED_DOCUMENT_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
    }
)


def normalized_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value cannot be blank")
    return stripped


class DocumentUploadIntentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    document_type: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    original_filename: str = Field(min_length=1, max_length=500)
    media_type: str = Field(max_length=150)
    byte_size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _title = field_validator("title")(normalized_text)

    @field_validator("original_filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        filename = normalized_text(value)
        if filename in {".", ".."} or "/" in filename or "\\" in filename:
            raise ValueError("original_filename must be a basename")
        if any(ord(character) < 32 for character in filename):
            raise ValueError("original_filename contains control characters")
        return filename

    @field_validator("media_type")
    @classmethod
    def supported_media_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_DOCUMENT_MEDIA_TYPES:
            raise ValueError("Unsupported document media type")
        return normalized


class DocumentUploadIntentRead(BaseModel):
    document_id: UUID
    document_version_id: UUID
    version: int
    expires_at: datetime
    upload_url: str
    upload_parameters: dict[str, Any]


class DocumentDownloadRead(BaseModel):
    document_version_id: UUID
    expires_at: datetime
    download_url: str


class DocumentUploadComplete(BaseModel):
    cloudinary_asset_id: str = Field(min_length=1, max_length=255)
    public_id: str = Field(min_length=1, max_length=500)
    resource_type: Literal["raw"]
    delivery_type: Literal["authenticated"] = "authenticated"
    provider_version: int = Field(gt=0)
    format: str | None = Field(default=None, max_length=50)
    byte_size: int = Field(gt=0)
    signature: str = Field(min_length=20, max_length=255)


class ScanResultCreate(BaseModel):
    scanner: str = Field(min_length=1, max_length=100)
    scanner_version: str = Field(min_length=1, max_length=100)
    status: Literal[ScanStatus.CLEAN, ScanStatus.INFECTED, ScanStatus.ERROR]
    result: dict[str, Any] = Field(default_factory=dict)

    _scanner = field_validator("scanner")(normalized_text)
    _scanner_version = field_validator("scanner_version")(normalized_text)


class CloudinaryAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cloudinary_asset_id: str
    public_id: str
    resource_type: str
    delivery_type: str
    provider_version: int
    format: str | None
    byte_size: int
    status: AssetStatus


class DocumentScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scanner: str
    scanner_version: str
    status: ScanStatus
    result: dict[str, Any]
    created_at: datetime


class DocumentPageWrite(BaseModel):
    page_number: int = Field(gt=0)
    source_label: str | None = Field(default=None, max_length=200)
    text: str = Field(max_length=2_000_000)
    width: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)
    height: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)
    ocr_confidence: Decimal | None = Field(
        default=None, ge=0, le=1, max_digits=5, decimal_places=4
    )
    tables: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


class ParseResultCreate(BaseModel):
    result_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    parser: str = Field(min_length=1, max_length=100)
    parser_version: str = Field(min_length=1, max_length=100)
    kind: ParseKind
    status: ParseStatus
    pages: list[DocumentPageWrite] = Field(default_factory=list, max_length=500)
    error_code: str | None = Field(
        default=None, max_length=100, pattern=r"^[a-z][a-z0-9_]*$"
    )
    error_detail: str | None = Field(default=None, max_length=5000)

    _parser = field_validator("parser")(normalized_text)
    _parser_version = field_validator("parser_version")(normalized_text)

    @model_validator(mode="after")
    def validate_outcome(self) -> "ParseResultCreate":
        if self.status is ParseStatus.COMPLETED:
            if not self.pages:
                raise ValueError("Completed parse results require at least one page")
            numbers = [page.page_number for page in self.pages]
            if numbers != list(range(1, len(numbers) + 1)):
                raise ValueError("page_number values must be consecutive starting at 1")
            if self.error_code is not None or self.error_detail is not None:
                raise ValueError("Completed parse results cannot include an error")
        else:
            if self.pages:
                raise ValueError("Failed parse results cannot include pages")
            if self.error_code is None:
                raise ValueError("Failed parse results require error_code")
        return self


class DocumentPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_number: int
    source_label: str | None
    text: str
    width: Decimal | None
    height: Decimal | None
    ocr_confidence: Decimal | None
    tables: list[dict[str, Any]]


class DocumentParseRead(BaseModel):
    id: UUID
    version: int
    result_key: str
    parser: str
    parser_version: str
    kind: ParseKind
    status: ParseStatus
    page_count: int
    content_digest: str
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    pages: list[DocumentPageRead]


class DocumentVersionRead(BaseModel):
    id: UUID
    version: int
    original_filename: str
    media_type: str
    byte_size: int
    sha256: str
    status: DocumentVersionStatus
    upload_expires_at: datetime | None
    created_at: datetime
    asset: CloudinaryAssetRead | None
    scans: list[DocumentScanRead]
    parses: list[DocumentParseRead]


class DocumentRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    document_type: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    versions: list[DocumentVersionRead]


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int
