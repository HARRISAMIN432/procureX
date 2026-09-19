from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.documents import (
    AssetStatus,
    DocumentStatus,
    DocumentVersionStatus,
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
