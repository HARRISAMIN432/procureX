from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.context import RequestContext, require_permission
from app.schemas.extractions import (
    ExtractionFinalize,
    ExtractionRead,
    FieldReviewCreate,
)
from app.services.extractions import (
    ExtractionConflictError,
    ExtractionNotFoundError,
    ExtractionValidationError,
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
