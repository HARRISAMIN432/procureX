from types import SimpleNamespace
from typing import cast

import pytest

from app.auth.context import RequestContext
from app.core.config import Settings
from app.models.documents import AssetStatus, DocumentVersionStatus, ParseKind, ParseStatus
from app.schemas.documents import DocumentUploadIntentCreate, ParseResultCreate
from app.services.documents import (
    DocumentConflictError,
    DocumentValidationError,
    _parse_result_digest,
    create_upload_intent,
    validate_download_state,
)


@pytest.mark.asyncio
async def test_upload_intent_enforces_configured_size_before_storage() -> None:
    context = cast(RequestContext, SimpleNamespace())
    settings = Settings(document_max_upload_bytes=100, _env_file=None)
    payload = DocumentUploadIntentCreate(
        title="Supplier quotation",
        document_type="supplier_quote",
        original_filename="quotation.pdf",
        media_type="application/pdf",
        byte_size=101,
        sha256="a" * 64,
    )

    with pytest.raises(DocumentValidationError, match="100-byte"):
        await create_upload_intent(context, settings, payload)


def test_parse_result_digest_is_deterministic_and_content_bound() -> None:
    payload = ParseResultCreate(
        result_key="parse-run-1",
        parser="pymupdf",
        parser_version="1.0",
        kind=ParseKind.NATIVE,
        status=ParseStatus.COMPLETED,
        pages=[{"page_number": 1, "text": "Quoted total: 100.00"}],
    )
    same = payload.model_copy(deep=True)
    changed = payload.model_copy(deep=True)
    changed.pages[0].text = "Quoted total: 101.00"

    assert _parse_result_digest(payload) == _parse_result_digest(same)
    assert _parse_result_digest(payload) != _parse_result_digest(changed)


def test_download_requires_clean_verified_asset_state() -> None:
    validate_download_state(DocumentVersionStatus.PARSED, AssetStatus.VERIFIED)
    with pytest.raises(DocumentConflictError, match="cannot be downloaded"):
        validate_download_state(DocumentVersionStatus.SCANNING, AssetStatus.UPLOADED)
    with pytest.raises(DocumentConflictError, match="deletion_pending"):
        validate_download_state(
            DocumentVersionStatus.REVIEWED, AssetStatus.DELETION_PENDING
        )
