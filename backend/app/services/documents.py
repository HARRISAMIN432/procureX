import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.core.cloudinary import (
    authenticated_document_upload_options,
    signed_document_upload_request,
    verify_document_upload_response,
)
from app.core.config import Settings
from app.models.documents import (
    AssetStatus,
    CloudinaryAsset,
    Document,
    DocumentPage,
    DocumentParse,
    DocumentScan,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    ParseStatus,
    ScanStatus,
)
from app.models.platform import ActorType, AuditEvent, Job, JobStatus, OutboxEvent
from app.schemas.documents import (
    CloudinaryAssetRead,
    DocumentList,
    DocumentPageRead,
    DocumentParseRead,
    DocumentRead,
    DocumentScanRead,
    DocumentUploadComplete,
    DocumentUploadIntentCreate,
    DocumentUploadIntentRead,
    DocumentVersionRead,
    ParseResultCreate,
    ScanResultCreate,
)


class DocumentNotFoundError(ValueError):
    pass


class DocumentConflictError(ValueError):
    pass


class DocumentValidationError(ValueError):
    pass


def _parse_result_digest(payload: ParseResultCreate) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _record_event(
    context: RequestContext,
    version: DocumentVersion,
    action: str,
    changes: dict[str, object],
    *,
    event_version: int | None = None,
) -> None:
    context.session.add_all(
        [
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action=action,
                object_type="document_version",
                object_id=version.id,
                object_version=version.version,
                changes=changes,
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="document_version",
                aggregate_id=version.id,
                aggregate_version=event_version or version.version,
                event_type=action,
                schema_version=1,
                payload={
                    "document_id": str(version.document_id),
                    "document_version_id": str(version.id),
                    "version": version.version,
                    "status": version.status.value,
                    **changes,
                },
                actor_id=context.user_id,
            ),
        ]
    )


async def create_upload_intent(
    context: RequestContext,
    settings: Settings,
    payload: DocumentUploadIntentCreate,
) -> DocumentUploadIntentRead:
    if payload.byte_size > settings.document_max_upload_bytes:
        raise DocumentValidationError(
            f"File exceeds the {settings.document_max_upload_bytes}-byte upload limit"
        )
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.document_upload_intent_ttl_seconds)
    document = Document(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        title=payload.title,
        document_type=payload.document_type,
        status=DocumentStatus.QUARANTINED,
        created_by_user_id=context.user_id,
    )
    version = DocumentVersion(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        document_id=document.id,
        version=1,
        original_filename=payload.original_filename,
        media_type=payload.media_type,
        byte_size=payload.byte_size,
        sha256=payload.sha256,
        status=DocumentVersionStatus.QUARANTINED,
        created_by_user_id=context.user_id,
        upload_expires_at=expires_at,
    )
    context.session.add_all([document, version])
    _record_event(
        context,
        version,
        "document.upload_intent_created",
        {
            "media_type": payload.media_type,
            "byte_size": payload.byte_size,
            "expires_at": expires_at.isoformat(),
        },
    )
    signed_request = signed_document_upload_request(
        settings, context.organization_id, version.id, timestamp=int(now.timestamp())
    )
    await context.session.flush()
    return DocumentUploadIntentRead(
        document_id=document.id,
        document_version_id=version.id,
        version=version.version,
        expires_at=expires_at,
        upload_url=signed_request["upload_url"],
        upload_parameters=signed_request["parameters"],
    )


async def _locked_version(
    context: RequestContext, document_id: uuid.UUID, version_id: uuid.UUID
) -> tuple[Document, DocumentVersion]:
    document = await context.session.scalar(
        select(Document)
        .where(
            Document.organization_id == context.organization_id,
            Document.id == document_id,
        )
        .with_for_update()
    )
    if document is None:
        raise DocumentNotFoundError("Document not found")
    version = await context.session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.document_id == document.id,
            DocumentVersion.id == version_id,
        )
        .with_for_update()
    )
    if version is None:
        raise DocumentNotFoundError("Document version not found")
    return document, version


async def complete_upload(
    context: RequestContext,
    settings: Settings,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: DocumentUploadComplete,
) -> DocumentRead:
    document, version = await _locked_version(context, document_id, version_id)
    if version.status is not DocumentVersionStatus.QUARANTINED:
        raise DocumentConflictError(f"Document version is {version.status.value}")
    now = datetime.now(UTC)
    if version.upload_expires_at is None or now > version.upload_expires_at.astimezone(UTC):
        raise DocumentValidationError("Upload intent has expired")
    expected_public_id = authenticated_document_upload_options(
        settings, context.organization_id, version.id
    )["public_id"]
    if payload.public_id != expected_public_id:
        raise DocumentValidationError("Uploaded asset does not match the reserved public ID")
    if payload.byte_size != version.byte_size:
        raise DocumentValidationError("Uploaded asset size does not match the declared size")
    if not verify_document_upload_response(
        settings,
        public_id=payload.public_id,
        provider_version=payload.provider_version,
        signature=payload.signature,
    ):
        raise DocumentValidationError("Cloudinary upload response signature is invalid")
    existing_asset = await context.session.scalar(
        select(CloudinaryAsset.id).where(
            (CloudinaryAsset.organization_id == context.organization_id)
            & (
                (CloudinaryAsset.document_version_id == version.id)
                | (CloudinaryAsset.cloudinary_asset_id == payload.cloudinary_asset_id)
            )
        )
    )
    if existing_asset is not None:
        raise DocumentConflictError("The upload is already registered")

    asset = CloudinaryAsset(
        organization_id=context.organization_id,
        document_version_id=version.id,
        cloudinary_asset_id=payload.cloudinary_asset_id,
        public_id=payload.public_id,
        resource_type=payload.resource_type,
        delivery_type=payload.delivery_type,
        provider_version=payload.provider_version,
        format=payload.format,
        byte_size=payload.byte_size,
        upload_response_signature=payload.signature,
        backup_enabled=False,
        status=AssetStatus.UPLOADED,
    )
    context.session.add(asset)
    version.status = DocumentVersionStatus.SCANNING
    document.status = DocumentStatus.SCANNING
    context.session.add(
        Job(
            organization_id=context.organization_id,
            job_type="document.scan",
            status=JobStatus.QUEUED,
            idempotency_key=f"document-scan:{version.id}",
            payload={
                "document_id": str(document.id),
                "document_version_id": str(version.id),
                "cloudinary_asset_id": payload.cloudinary_asset_id,
            },
        )
    )
    _record_event(
        context,
        version,
        "document.upload_completed",
        {
            "cloudinary_asset_id": payload.cloudinary_asset_id,
            "public_id": payload.public_id,
        },
    )
    await context.session.flush()
    return await read_document(context, document.id)


async def record_scan_result(
    context: RequestContext,
    version_id: uuid.UUID,
    payload: ScanResultCreate,
) -> DocumentRead:
    candidate = await context.session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.id == version_id,
        )
    )
    if candidate is None:
        raise DocumentNotFoundError("Document version not found")
    document, version = await _locked_version(context, candidate.document_id, version_id)
    if version.status is not DocumentVersionStatus.SCANNING:
        raise DocumentConflictError(f"Document version is {version.status.value}")
    duplicate = await context.session.scalar(
        select(DocumentScan.id).where(
            DocumentScan.organization_id == context.organization_id,
            DocumentScan.document_version_id == version.id,
            DocumentScan.scanner == payload.scanner,
            DocumentScan.scanner_version == payload.scanner_version,
        )
    )
    if duplicate is not None:
        raise DocumentConflictError("This scanner result is already recorded")
    scan_attempts = await context.session.scalar(
        select(func.count(DocumentScan.id)).where(
            DocumentScan.organization_id == context.organization_id,
            DocumentScan.document_version_id == version.id,
        )
    )
    asset = await context.session.scalar(
        select(CloudinaryAsset)
        .where(
            CloudinaryAsset.organization_id == context.organization_id,
            CloudinaryAsset.document_version_id == version.id,
        )
        .with_for_update()
    )
    if asset is None:
        raise DocumentConflictError("Document version has no registered asset")

    scan = DocumentScan(
        organization_id=context.organization_id,
        document_version_id=version.id,
        scanner=payload.scanner,
        scanner_version=payload.scanner_version,
        status=ScanStatus(payload.status),
        result=payload.result,
    )
    context.session.add(scan)
    job = await context.session.scalar(
        select(Job)
        .where(
            Job.organization_id == context.organization_id,
            Job.idempotency_key == f"document-scan:{version.id}",
        )
        .with_for_update()
    )
    event_action = "document.scan_failed"
    if payload.status is ScanStatus.CLEAN:
        asset.status = AssetStatus.VERIFIED
        version.status = DocumentVersionStatus.PARSING
        document.status = DocumentStatus.READY
        event_action = "document.scan_clean"
        if job is not None:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            job.result = {"scan_status": payload.status.value}
        context.session.add(
            Job(
                organization_id=context.organization_id,
                job_type="document.parse",
                status=JobStatus.QUEUED,
                idempotency_key=f"document-parse:{version.id}",
                payload={
                    "document_id": str(document.id),
                    "document_version_id": str(version.id),
                    "media_type": version.media_type,
                    "sha256": version.sha256,
                },
            )
        )
    elif payload.status is ScanStatus.INFECTED:
        version.status = DocumentVersionStatus.REJECTED
        document.status = DocumentStatus.REJECTED
        event_action = "document.scan_infected"
        if job is not None:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            job.result = {"scan_status": payload.status.value}
    elif job is not None:
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(UTC)
        job.error_code = "scanner_error"
        job.error_detail = "Scanner reported an error; asset remains quarantined"
    _record_event(
        context,
        version,
        event_action,
        {
            "scanner": payload.scanner,
            "scanner_version": payload.scanner_version,
            "scan_status": payload.status.value,
        },
        event_version=(scan_attempts or 0) + 1,
    )
    await context.session.flush()
    return await read_document(context, document.id)


async def record_parse_result(
    context: RequestContext,
    version_id: uuid.UUID,
    payload: ParseResultCreate,
) -> DocumentRead:
    candidate = await context.session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.id == version_id,
        )
    )
    if candidate is None:
        raise DocumentNotFoundError("Document version not found")
    document, version = await _locked_version(context, candidate.document_id, version_id)
    digest = _parse_result_digest(payload)
    existing = await context.session.scalar(
        select(DocumentParse).where(
            DocumentParse.organization_id == context.organization_id,
            DocumentParse.document_version_id == version.id,
            DocumentParse.result_key == payload.result_key,
        )
    )
    if existing is not None:
        if existing.content_digest != digest:
            raise DocumentConflictError("Parse result key was reused with different content")
        return await read_document(context, document.id)
    if version.status is not DocumentVersionStatus.PARSING:
        raise DocumentConflictError(f"Document version is {version.status.value}")
    asset_status = await context.session.scalar(
        select(CloudinaryAsset.status).where(
            CloudinaryAsset.organization_id == context.organization_id,
            CloudinaryAsset.document_version_id == version.id,
        )
    )
    if asset_status is not AssetStatus.VERIFIED:
        raise DocumentConflictError("Only a verified asset can be parsed")
    current_version = await context.session.scalar(
        select(func.max(DocumentParse.version)).where(
            DocumentParse.organization_id == context.organization_id,
            DocumentParse.document_version_id == version.id,
        )
    )
    parse = DocumentParse(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        document_version_id=version.id,
        version=(current_version or 0) + 1,
        result_key=payload.result_key,
        parser=payload.parser,
        parser_version=payload.parser_version,
        kind=payload.kind,
        status=payload.status,
        page_count=len(payload.pages),
        content_digest=digest,
        error_code=payload.error_code,
        error_detail=payload.error_detail,
    )
    context.session.add(parse)
    context.session.add_all(
        [
            DocumentPage(
                organization_id=context.organization_id,
                document_version_id=version.id,
                parse_id=parse.id,
                page_number=page.page_number,
                source_label=page.source_label,
                text=page.text,
                width=page.width,
                height=page.height,
                ocr_confidence=page.ocr_confidence,
                tables=page.tables,
            )
            for page in payload.pages
        ]
    )
    parse_job = await context.session.scalar(
        select(Job)
        .where(
            Job.organization_id == context.organization_id,
            Job.idempotency_key == f"document-parse:{version.id}",
        )
        .with_for_update()
    )
    if payload.status is ParseStatus.COMPLETED:
        version.status = DocumentVersionStatus.PARSED
        event_action = "document.parse_completed"
        if parse_job is not None:
            parse_job.status = JobStatus.COMPLETED
            parse_job.completed_at = datetime.now(UTC)
            parse_job.result = {
                "parse_id": str(parse.id),
                "page_count": len(payload.pages),
                "content_digest": digest,
            }
    else:
        event_action = "document.parse_failed"
        if parse_job is not None:
            parse_job.status = JobStatus.FAILED
            parse_job.completed_at = datetime.now(UTC)
            parse_job.error_code = payload.error_code
            parse_job.error_detail = payload.error_detail
    _record_event(
        context,
        version,
        event_action,
        {
            "parse_id": str(parse.id),
            "parse_version": parse.version,
            "parser": payload.parser,
            "parser_version": payload.parser_version,
            "parse_status": payload.status.value,
            "page_count": len(payload.pages),
            "content_digest": digest,
        },
        event_version=parse.version,
    )
    await context.session.flush()
    return await read_document(context, document.id)


async def read_document(context: RequestContext, document_id: uuid.UUID) -> DocumentRead:
    document = await context.session.scalar(
        select(Document).where(
            Document.organization_id == context.organization_id,
            Document.id == document_id,
        )
    )
    if document is None:
        raise DocumentNotFoundError("Document not found")
    versions = list(
        await context.session.scalars(
            select(DocumentVersion)
            .where(
                DocumentVersion.organization_id == context.organization_id,
                DocumentVersion.document_id == document.id,
            )
            .order_by(DocumentVersion.version)
        )
    )
    version_views: list[DocumentVersionRead] = []
    for version in versions:
        asset = await context.session.scalar(
            select(CloudinaryAsset).where(
                CloudinaryAsset.organization_id == context.organization_id,
                CloudinaryAsset.document_version_id == version.id,
            )
        )
        scans = list(
            await context.session.scalars(
                select(DocumentScan)
                .where(
                    DocumentScan.organization_id == context.organization_id,
                    DocumentScan.document_version_id == version.id,
                )
                .order_by(DocumentScan.created_at, DocumentScan.id)
            )
        )
        parses = list(
            await context.session.scalars(
                select(DocumentParse)
                .where(
                    DocumentParse.organization_id == context.organization_id,
                    DocumentParse.document_version_id == version.id,
                )
                .order_by(DocumentParse.version)
            )
        )
        parse_views: list[DocumentParseRead] = []
        for parse in parses:
            pages = list(
                await context.session.scalars(
                    select(DocumentPage)
                    .where(
                        DocumentPage.organization_id == context.organization_id,
                        DocumentPage.parse_id == parse.id,
                    )
                    .order_by(DocumentPage.page_number)
                )
            )
            parse_views.append(
                DocumentParseRead(
                    id=parse.id,
                    version=parse.version,
                    result_key=parse.result_key,
                    parser=parse.parser,
                    parser_version=parse.parser_version,
                    kind=parse.kind,
                    status=parse.status,
                    page_count=parse.page_count,
                    content_digest=parse.content_digest,
                    error_code=parse.error_code,
                    error_detail=parse.error_detail,
                    created_at=parse.created_at,
                    pages=[DocumentPageRead.model_validate(page) for page in pages],
                )
            )
        version_views.append(
            DocumentVersionRead(
                id=version.id,
                version=version.version,
                original_filename=version.original_filename,
                media_type=version.media_type,
                byte_size=version.byte_size,
                sha256=version.sha256,
                status=version.status,
                upload_expires_at=version.upload_expires_at,
                created_at=version.created_at,
                asset=CloudinaryAssetRead.model_validate(asset) if asset else None,
                scans=[DocumentScanRead.model_validate(scan) for scan in scans],
                parses=parse_views,
            )
        )
    return DocumentRead(
        id=document.id,
        organization_id=document.organization_id,
        title=document.title,
        document_type=document.document_type,
        status=document.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
        versions=version_views,
    )


async def list_documents(context: RequestContext, limit: int, offset: int) -> DocumentList:
    total = await context.session.scalar(
        select(func.count(Document.id)).where(
            Document.organization_id == context.organization_id
        )
    )
    document_ids = list(
        await context.session.scalars(
            select(Document.id)
            .where(Document.organization_id == context.organization_id)
            .order_by(Document.created_at.desc(), Document.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return DocumentList(
        items=[await read_document(context, document_id) for document_id in document_ids],
        total=total or 0,
    )
