from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.documents import ParseKind, ParseStatus, ScanStatus
from app.schemas.documents import (
    DocumentUploadComplete,
    DocumentUploadIntentCreate,
    ParseResultCreate,
    ScanResultCreate,
)


def valid_intent() -> dict[str, object]:
    return {
        "title": "Supplier quotation",
        "document_type": "supplier_quote",
        "original_filename": "quotation.pdf",
        "media_type": "application/pdf",
        "byte_size": 1024,
        "sha256": "a" * 64,
    }


def test_upload_intent_rejects_path_filename() -> None:
    with pytest.raises(ValidationError, match="basename"):
        DocumentUploadIntentCreate(**{**valid_intent(), "original_filename": "../quote.pdf"})


def test_upload_intent_rejects_unsupported_media_type() -> None:
    with pytest.raises(ValidationError, match="Unsupported"):
        DocumentUploadIntentCreate(**{**valid_intent(), "media_type": "application/zip"})


def test_upload_completion_enforces_private_raw_asset() -> None:
    with pytest.raises(ValidationError):
        DocumentUploadComplete(
            cloudinary_asset_id=str(uuid4()),
            public_id="procurex/test/asset",
            resource_type="image",
            delivery_type="upload",
            provider_version=1,
            byte_size=1024,
            signature="a" * 40,
        )


def test_scan_result_cannot_be_pending() -> None:
    with pytest.raises(ValidationError):
        ScanResultCreate(
            scanner="clamav",
            scanner_version="1.4",
            status=ScanStatus.PENDING,
        )


def test_completed_parse_requires_consecutive_pages() -> None:
    with pytest.raises(ValidationError, match="consecutive"):
        ParseResultCreate(
            result_key="parse-run-1",
            parser="pymupdf",
            parser_version="1.0",
            kind=ParseKind.NATIVE,
            status=ParseStatus.COMPLETED,
            pages=[
                {"page_number": 1, "text": "First"},
                {"page_number": 3, "text": "Third"},
            ],
        )


def test_failed_parse_requires_error_and_no_pages() -> None:
    with pytest.raises(ValidationError, match="error_code"):
        ParseResultCreate(
            result_key="parse-run-1",
            parser="pymupdf",
            parser_version="1.0",
            kind=ParseKind.NATIVE,
            status=ParseStatus.FAILED,
        )


def test_completed_parse_accepts_ocr_evidence_source() -> None:
    payload = ParseResultCreate(
        result_key="parse-run-1",
        parser="tesseract",
        parser_version="5.4",
        kind=ParseKind.OCR,
        status=ParseStatus.COMPLETED,
        pages=[
            {
                "page_number": 1,
                "source_label": "Page 1",
                "text": "Total: PKR 100.00",
                "ocr_confidence": "0.9750",
                "tables": [{"rows": [["Total", "100.00"]]}],
            }
        ],
    )
    assert payload.pages[0].ocr_confidence is not None
