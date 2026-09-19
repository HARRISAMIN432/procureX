from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.context import RequestContext, require_permission
from app.core.cloudinary import CloudinaryConfigurationError
from app.core.config import Settings, get_settings
from app.schemas.documents import (
    DocumentList,
    DocumentRead,
    DocumentUploadComplete,
    DocumentUploadIntentCreate,
    DocumentUploadIntentRead,
    ParseResultCreate,
    ScanResultCreate,
)
from app.services.documents import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentValidationError,
    complete_upload,
    create_upload_intent,
    list_documents,
    read_document,
    record_parse_result,
    record_scan_result,
)

router = APIRouter(prefix="/documents", tags=["documents"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": str(exc)},
        ) from exc
    except DocumentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "document_conflict", "message": str(exc)},
        ) from exc
    except DocumentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "document_validation_failed", "message": str(exc)},
        ) from exc
    except CloudinaryConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "document_storage_unavailable", "message": str(exc)},
        ) from exc


@router.post(
    "/upload-intents",
    response_model=DocumentUploadIntentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_intent(
    payload: DocumentUploadIntentCreate,
    context: Annotated[RequestContext, Depends(require_permission("documents.write"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentUploadIntentRead:
    return await execute(lambda: create_upload_intent(context, settings, payload))


@router.post(
    "/{document_id}/versions/{version_id}/complete-upload",
    response_model=DocumentRead,
)
async def finish_upload(
    document_id: UUID,
    version_id: UUID,
    payload: DocumentUploadComplete,
    context: Annotated[RequestContext, Depends(require_permission("documents.write"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentRead:
    return await execute(
        lambda: complete_upload(context, settings, document_id, version_id, payload)
    )


@router.post("/versions/{version_id}/scan-results", response_model=DocumentRead)
async def scan_result(
    version_id: UUID,
    payload: ScanResultCreate,
    context: Annotated[RequestContext, Depends(require_permission("documents.scan"))],
) -> DocumentRead:
    return await execute(lambda: record_scan_result(context, version_id, payload))


@router.post("/versions/{version_id}/parse-results", response_model=DocumentRead)
async def parse_result(
    version_id: UUID,
    payload: ParseResultCreate,
    context: Annotated[RequestContext, Depends(require_permission("documents.process"))],
) -> DocumentRead:
    return await execute(lambda: record_parse_result(context, version_id, payload))


@router.get("", response_model=DocumentList)
async def list_all(
    context: Annotated[RequestContext, Depends(require_permission("documents.read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    return await list_documents(context, limit, offset)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_one(
    document_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("documents.read"))],
) -> DocumentRead:
    return await execute(lambda: read_document(context, document_id))
