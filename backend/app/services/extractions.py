import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.models.ai import AnalysisRun, AnalysisRunStatus
from app.models.documents import (
    DocumentPage,
    DocumentParse,
    DocumentVersion,
    DocumentVersionStatus,
    ParseStatus,
)
from app.models.extractions import (
    EvidenceAnchor,
    ExtractedField,
    ExtractedFieldStatus,
    Extraction,
    ExtractionStatus,
    FieldReview,
    ReviewAction,
)
from app.models.platform import ActorType, AuditEvent, Job, JobStatus, OutboxEvent
from app.schemas.extractions import (
    EvidenceAnchorRead,
    ExtractedFieldRead,
    ExtractionFinalize,
    ExtractionRead,
    ExtractionResultCreate,
    FieldReviewCreate,
    FieldReviewRead,
)


class ExtractionNotFoundError(ValueError):
    pass


class ExtractionConflictError(ValueError):
    pass


class ExtractionValidationError(ValueError):
    pass


def extraction_result_digest(payload: ExtractionResultCreate) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _record_event(
    context: RequestContext,
    extraction: Extraction,
    action: str,
    changes: dict[str, object],
) -> None:
    context.session.add_all(
        [
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action=action,
                object_type="extraction",
                object_id=extraction.id,
                object_version=extraction.revision,
                changes=changes,
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="extraction",
                aggregate_id=extraction.id,
                aggregate_version=extraction.revision,
                event_type=action,
                schema_version=1,
                payload={
                    "extraction_id": str(extraction.id),
                    "document_version_id": str(extraction.document_version_id),
                    "revision": extraction.revision,
                    "status": extraction.status.value,
                    **changes,
                },
                actor_id=context.user_id,
            ),
        ]
    )


async def create_extraction(
    context: RequestContext,
    version_id: uuid.UUID,
    payload: ExtractionResultCreate,
) -> ExtractionRead:
    version = await context.session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.id == version_id,
        )
        .with_for_update()
    )
    if version is None:
        raise ExtractionNotFoundError("Document version not found")
    digest = extraction_result_digest(payload)
    existing = await context.session.scalar(
        select(Extraction).where(
            Extraction.organization_id == context.organization_id,
            Extraction.document_version_id == version.id,
            Extraction.result_key == payload.result_key,
        )
    )
    if existing is not None:
        if existing.content_digest != digest:
            raise ExtractionConflictError(
                "Extraction result key was reused with different content"
            )
        return await read_extraction(context, existing.id)
    if version.status is not DocumentVersionStatus.PARSED:
        raise ExtractionConflictError(f"Document version is {version.status.value}")
    parse = await context.session.scalar(
        select(DocumentParse).where(
            DocumentParse.organization_id == context.organization_id,
            DocumentParse.document_version_id == version.id,
            DocumentParse.id == payload.parse_id,
            DocumentParse.status == ParseStatus.COMPLETED,
        )
    )
    if parse is None:
        raise ExtractionValidationError("Completed source parse not found")
    pages = {
        page.page_number: page
        for page in await context.session.scalars(
            select(DocumentPage).where(
                DocumentPage.organization_id == context.organization_id,
                DocumentPage.document_version_id == version.id,
                DocumentPage.parse_id == parse.id,
            )
        )
    }
    referenced_pages = {
        anchor.page_number for field in payload.fields for anchor in field.anchors
    }
    if not referenced_pages.issubset(pages):
        raise ExtractionValidationError("One or more evidence anchors reference an unknown page")
    current_version = await context.session.scalar(
        select(func.max(Extraction.version)).where(
            Extraction.organization_id == context.organization_id,
            Extraction.document_version_id == version.id,
        )
    )
    extraction_id = uuid.uuid4()
    analysis_run_id = uuid.uuid4()
    extraction_version = (current_version or 0) + 1
    now = datetime.now(UTC)
    analysis_run = AnalysisRun(
        id=analysis_run_id,
        organization_id=context.organization_id,
        graph_name="document_analysis_graph",
        graph_version="1",
        thread_id=f"document-analysis:{version.id}:{payload.result_key}",
        document_version_id=version.id,
        source_digest=parse.content_digest,
        status=AnalysisRunStatus.AWAITING_REVIEW,
        input={
            "document_version_id": str(version.id),
            "parse_id": str(parse.id),
            "extraction_id": str(extraction_id),
            "source_digest": parse.content_digest,
        },
        started_at=now,
        created_by_user_id=context.user_id,
    )
    extraction = Extraction(
        id=extraction_id,
        organization_id=context.organization_id,
        document_version_id=version.id,
        parse_id=parse.id,
        analysis_run_id=analysis_run_id,
        version=extraction_version,
        revision=1,
        result_key=payload.result_key,
        schema_name=payload.schema_name,
        schema_version=payload.schema_version,
        status=ExtractionStatus.AWAITING_REVIEW,
        source_digest=parse.content_digest,
        content_digest=digest,
    )
    context.session.add_all([analysis_run, extraction])
    field_ids = {field.field_key: uuid.uuid4() for field in payload.fields}
    context.session.add_all(
        [
            ExtractedField(
                id=field_ids[field.field_key],
                organization_id=context.organization_id,
                document_version_id=version.id,
                extraction_id=extraction.id,
                field_key=field.field_key,
                label=field.label,
                data_type=field.data_type,
                raw_value=field.raw_value,
                normalized_value=field.normalized_value,
                status=field.status,
                is_critical=field.is_critical,
                confidence=field.confidence,
            )
            for field in payload.fields
        ]
    )
    context.session.add_all(
        [
            EvidenceAnchor(
                organization_id=context.organization_id,
                document_version_id=version.id,
                parse_id=parse.id,
                extraction_id=extraction.id,
                field_id=field_ids[field.field_key],
                page_id=pages[anchor.page_number].id,
                quoted_text=anchor.quoted_text,
                bounding_box=(
                    anchor.bounding_box.model_dump(mode="json")
                    if anchor.bounding_box is not None
                    else None
                ),
                cell_range=anchor.cell_range,
            )
            for field in payload.fields
            for anchor in field.anchors
        ]
    )
    version.status = DocumentVersionStatus.EXTRACTED
    extraction_job = await context.session.scalar(
        select(Job)
        .where(
            Job.organization_id == context.organization_id,
            Job.idempotency_key == f"document-extract:{version.id}:{parse.id}",
        )
        .with_for_update()
    )
    if extraction_job is not None:
        extraction_job.status = JobStatus.COMPLETED
        extraction_job.completed_at = now
        extraction_job.result = {
            "extraction_id": str(extraction.id),
            "content_digest": digest,
            "field_count": len(payload.fields),
        }
    _record_event(
        context,
        extraction,
        "document.extraction_awaiting_review",
        {
            "field_count": len(payload.fields),
            "critical_field_count": sum(field.is_critical for field in payload.fields),
            "content_digest": digest,
            "source_digest": parse.content_digest,
        },
    )
    await context.session.flush()
    return await read_extraction(context, extraction.id)


async def _locked_extraction(context: RequestContext, extraction_id: uuid.UUID) -> Extraction:
    extraction = await context.session.scalar(
        select(Extraction)
        .where(
            Extraction.organization_id == context.organization_id,
            Extraction.id == extraction_id,
        )
        .with_for_update()
    )
    if extraction is None:
        raise ExtractionNotFoundError("Extraction not found")
    return extraction


def _check_revision(extraction: Extraction, expected_revision: int) -> None:
    if extraction.revision != expected_revision:
        raise ExtractionConflictError(
            f"Expected revision {expected_revision}, current revision is {extraction.revision}"
        )


def unresolved_field_keys(fields: list[ExtractedField]) -> list[str]:
    return [
        field.field_key
        for field in fields
        if field.status not in {ExtractedFieldStatus.VERIFIED, ExtractedFieldStatus.REJECTED}
        or (field.is_critical and field.status is not ExtractedFieldStatus.VERIFIED)
    ]


async def review_field(
    context: RequestContext,
    extraction_id: uuid.UUID,
    field_id: uuid.UUID,
    payload: FieldReviewCreate,
) -> ExtractionRead:
    extraction = await _locked_extraction(context, extraction_id)
    _check_revision(extraction, payload.expected_revision)
    if extraction.status is ExtractionStatus.COMPLETED:
        raise ExtractionConflictError("Completed extraction reviews are immutable")
    field = await context.session.scalar(
        select(ExtractedField)
        .where(
            ExtractedField.organization_id == context.organization_id,
            ExtractedField.extraction_id == extraction.id,
            ExtractedField.id == field_id,
        )
        .with_for_update()
    )
    if field is None:
        raise ExtractionNotFoundError("Extracted field not found")
    previous_status = field.status
    previous_value = field.normalized_value
    if payload.action is ReviewAction.REJECT:
        reviewed_status = ExtractedFieldStatus.REJECTED
        reviewed_value = field.normalized_value
    else:
        reviewed_status = ExtractedFieldStatus.VERIFIED
        reviewed_value = (
            payload.normalized_value
            if payload.action is ReviewAction.CORRECT
            else field.normalized_value if field.normalized_value is not None else field.raw_value
        )
        if reviewed_value is None:
            raise ExtractionValidationError("A verified field requires a value")
    field.status = reviewed_status
    field.normalized_value = reviewed_value
    context.session.add(
        FieldReview(
            organization_id=context.organization_id,
            extraction_id=extraction.id,
            field_id=field.id,
            action=payload.action,
            previous_status=previous_status.value,
            previous_value=previous_value,
            reviewed_status=reviewed_status.value,
            reviewed_value=reviewed_value,
            reason=payload.reason,
            reviewed_by_user_id=context.user_id,
        )
    )
    extraction.status = ExtractionStatus.IN_REVIEW
    extraction.revision += 1
    _record_event(
        context,
        extraction,
        "document.field_reviewed",
        {
            "field_id": str(field.id),
            "field_key": field.field_key,
            "action": payload.action.value,
            "previous_status": previous_status.value,
            "reviewed_status": reviewed_status.value,
        },
    )
    await context.session.flush()
    return await read_extraction(context, extraction.id)


async def finalize_extraction(
    context: RequestContext,
    extraction_id: uuid.UUID,
    payload: ExtractionFinalize,
) -> ExtractionRead:
    extraction = await _locked_extraction(context, extraction_id)
    _check_revision(extraction, payload.expected_revision)
    if extraction.status is ExtractionStatus.COMPLETED:
        raise ExtractionConflictError("Extraction is already completed")
    fields = list(
        await context.session.scalars(
            select(ExtractedField).where(
                ExtractedField.organization_id == context.organization_id,
                ExtractedField.extraction_id == extraction.id,
            )
        )
    )
    unresolved = unresolved_field_keys(fields)
    if unresolved:
        raise ExtractionValidationError(
            f"Unresolved fields block finalization: {', '.join(sorted(unresolved))}"
        )
    now = datetime.now(UTC)
    extraction.status = ExtractionStatus.COMPLETED
    extraction.completed_at = now
    extraction.revision += 1
    version = await context.session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.id == extraction.document_version_id,
        )
        .with_for_update()
    )
    if version is None:
        raise ExtractionNotFoundError("Document version not found")
    if version.status is not DocumentVersionStatus.EXTRACTED:
        raise ExtractionConflictError(f"Document version is {version.status.value}")
    version.status = DocumentVersionStatus.REVIEWED
    analysis_run = await context.session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.organization_id == context.organization_id,
            AnalysisRun.id == extraction.analysis_run_id,
        )
        .with_for_update()
    )
    if analysis_run is None:
        raise ExtractionNotFoundError("Analysis run not found")
    analysis_run.status = AnalysisRunStatus.COMPLETED
    analysis_run.completed_at = now
    analysis_run.output = {
        "extraction_id": str(extraction.id),
        "extraction_revision": extraction.revision,
        "verified_field_ids": [
            str(field.id) for field in fields if field.status is ExtractedFieldStatus.VERIFIED
        ],
    }
    _record_event(
        context,
        extraction,
        "document.review_completed",
        {
            "verified_field_count": sum(
                field.status is ExtractedFieldStatus.VERIFIED for field in fields
            ),
            "rejected_field_count": sum(
                field.status is ExtractedFieldStatus.REJECTED for field in fields
            ),
        },
    )
    await context.session.flush()
    return await read_extraction(context, extraction.id)


async def read_extraction(context: RequestContext, extraction_id: uuid.UUID) -> ExtractionRead:
    extraction = await context.session.scalar(
        select(Extraction).where(
            Extraction.organization_id == context.organization_id,
            Extraction.id == extraction_id,
        )
    )
    if extraction is None:
        raise ExtractionNotFoundError("Extraction not found")
    fields = list(
        await context.session.scalars(
            select(ExtractedField)
            .where(
                ExtractedField.organization_id == context.organization_id,
                ExtractedField.extraction_id == extraction.id,
            )
            .order_by(ExtractedField.field_key)
        )
    )
    field_views: list[ExtractedFieldRead] = []
    for field in fields:
        anchors = list(
            await context.session.scalars(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.organization_id == context.organization_id,
                    EvidenceAnchor.extraction_id == extraction.id,
                    EvidenceAnchor.field_id == field.id,
                )
            )
        )
        reviews = list(
            await context.session.scalars(
                select(FieldReview)
                .where(
                    FieldReview.organization_id == context.organization_id,
                    FieldReview.extraction_id == extraction.id,
                    FieldReview.field_id == field.id,
                )
                .order_by(FieldReview.reviewed_at, FieldReview.id)
            )
        )
        field_views.append(
            ExtractedFieldRead(
                id=field.id,
                field_key=field.field_key,
                label=field.label,
                data_type=field.data_type,
                raw_value=field.raw_value,
                normalized_value=field.normalized_value,
                status=field.status,
                is_critical=field.is_critical,
                confidence=field.confidence,
                anchors=[EvidenceAnchorRead.model_validate(anchor) for anchor in anchors],
                reviews=[FieldReviewRead.model_validate(review) for review in reviews],
            )
        )
    return ExtractionRead(
        id=extraction.id,
        document_version_id=extraction.document_version_id,
        parse_id=extraction.parse_id,
        analysis_run_id=extraction.analysis_run_id,
        version=extraction.version,
        revision=extraction.revision,
        result_key=extraction.result_key,
        schema_name=extraction.schema_name,
        schema_version=extraction.schema_version,
        status=extraction.status,
        source_digest=extraction.source_digest,
        content_digest=extraction.content_digest,
        created_at=extraction.created_at,
        completed_at=extraction.completed_at,
        fields=field_views,
    )
