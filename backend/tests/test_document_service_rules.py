from types import SimpleNamespace
from typing import cast

import pytest

from app.auth.context import RequestContext
from app.core.config import Settings
from app.schemas.documents import DocumentUploadIntentCreate
from app.services.documents import DocumentValidationError, create_upload_intent


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
