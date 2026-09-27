from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth.context import RequestContext, require_permission
from app.models.documents import DocumentPage
from app.models.extractions import ExtractedFieldStatus, Extraction
from app.schemas.extractions import (
    EvidenceAnchorWrite,
    ExtractedFieldWrite,
    ExtractionFinalize,
    ExtractionRead,
    ExtractionResultCreate,
    FieldReviewCreate,
    ManualExtractionCreate,
)
from app.services.extractions import (
    ExtractionConflictError,
    ExtractionNotFoundError,
    ExtractionValidationError,
    create_extraction,
    finalize_extraction,
    read_extraction,
    review_field,
)

router = APIRouter(tags=["extractions"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except ExtractionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "extraction_not_found", "message": str(exc)},
        ) from exc
    except ExtractionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "extraction_conflict", "message": str(exc)},
        ) from exc
    except ExtractionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "extraction_validation_failed", "message": str(exc)},
        ) from exc


@router.get("/extractions/{extraction_id}", response_model=ExtractionRead)
async def get_one(
    extraction_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("documents.read"))],
) -> ExtractionRead:
    return await execute(lambda: read_extraction(context, extraction_id))


@router.get("/documents/versions/{version_id}/extractions", response_model=list[ExtractionRead])
async def list_for_version(
    version_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("documents.read"))],
) -> list[ExtractionRead]:
    ids = list(
        await context.session.scalars(
            select(Extraction.id)
            .where(
                Extraction.organization_id == context.organization_id,
                Extraction.document_version_id == version_id,
            )
            .order_by(Extraction.version.desc())
        )
    )
    return [await read_extraction(context, item) for item in ids]


@router.post(
    "/documents/versions/{version_id}/manual-extractions",
    response_model=ExtractionRead,
    status_code=status.HTTP_201_CREATED,
)
async def stage_manual_extraction(
    version_id: UUID,
    payload: ManualExtractionCreate,
    context: Annotated[RequestContext, Depends(require_permission("documents.review"))],
) -> ExtractionRead:
    pages = list(
        await context.session.scalars(
            select(DocumentPage).where(
                DocumentPage.organization_id == context.organization_id,
                DocumentPage.document_version_id == version_id,
                DocumentPage.parse_id == payload.parse_id,
            )
        )
    )
    page_text = {page.page_number: page.text for page in pages}
    if any(
        field.page_number not in page_text
        or field.quoted_text.strip() not in page_text[field.page_number]
        for field in payload.fields
    ):
        raise HTTPException(
            status_code=422,
            detail="Each quoted source must appear on its selected parsed page",
        )
    result = ExtractionResultCreate(
        parse_id=payload.parse_id,
        result_key=f"manual:{uuid4()}",
        schema_name=payload.schema_name,
        schema_version="1",
        fields=[
            ExtractedFieldWrite(
                field_key=field.field_key,
                label=field.label,
                data_type="string",
                raw_value=field.value,
                normalized_value=field.value,
                status=ExtractedFieldStatus.PROPOSED,
                is_critical=field.is_critical,
                anchors=[
                    EvidenceAnchorWrite(
                        page_number=field.page_number,
                        quoted_text=field.quoted_text.strip(),
                    )
                ],
            )
            for field in payload.fields
        ],
    )
    return await execute(lambda: create_extraction(context, version_id, result))


@router.post(
    "/extractions/{extraction_id}/fields/{field_id}/review",
    response_model=ExtractionRead,
)
async def review(
    extraction_id: UUID,
    field_id: UUID,
    payload: FieldReviewCreate,
    context: Annotated[RequestContext, Depends(require_permission("documents.review"))],
) -> ExtractionRead:
    return await execute(lambda: review_field(context, extraction_id, field_id, payload))


@router.post("/extractions/{extraction_id}/finalize", response_model=ExtractionRead)
async def finalize(
    extraction_id: UUID,
    payload: ExtractionFinalize,
    context: Annotated[RequestContext, Depends(require_permission("documents.review"))],
) -> ExtractionRead:
    return await execute(lambda: finalize_extraction(context, extraction_id, payload))
