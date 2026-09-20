import asyncio
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.auth.context import RequestContext
from app.core.cloudinary import signed_document_download_url
from app.core.config import get_settings
from app.core.database import close_database, tenant_transaction
from app.models.documents import CloudinaryAsset, DocumentVersion, DocumentVersionStatus, ScanStatus
from app.models.platform import ActorType, Job, JobStatus
from app.schemas.documents import ScanResultCreate
from app.services.documents import record_scan_result
from app.workers.celery_app import celery_app
from app.workers.document_security import download_verified_asset, scan_with_clamav


def enqueue_document_scan(organization_id: uuid.UUID, version_id: uuid.UUID) -> None:
    run_document_scan.apply_async(args=[str(organization_id), str(version_id)])


async def _record_failure(
    organization_id: uuid.UUID, version_id: uuid.UUID, exc: Exception
) -> None:
    async with tenant_transaction(organization_id) as session:
        job = await session.scalar(
            select(Job)
            .where(
                Job.organization_id == organization_id,
                Job.idempotency_key == f"document-scan:{version_id}",
            )
            .with_for_update()
        )
        if job is None or job.status is JobStatus.COMPLETED:
            return
        exhausted = job.attempts >= job.max_attempts
        job.status = JobStatus.FAILED if exhausted else JobStatus.RETRY_SCHEDULED
        job.error_code = type(exc).__name__[:100]
        job.error_detail = "Document security processing failed; asset remains quarantined"
        if exhausted:
            job.completed_at = datetime.now(UTC)


async def _execute_scan(organization_id: uuid.UUID, version_id: uuid.UUID) -> dict[str, object]:
    settings = get_settings()
    async with tenant_transaction(organization_id) as session:
        job = await session.scalar(
            select(Job)
            .where(
                Job.organization_id == organization_id,
                Job.idempotency_key == f"document-scan:{version_id}",
            )
            .with_for_update()
        )
        if job is None:
            raise ValueError("Document scan job not found")
        if job.status is JobStatus.COMPLETED:
            return job.result or {"status": "completed"}
        if job.status in {JobStatus.CANCELLED, JobStatus.FAILED}:
            raise ValueError(f"Document scan job is {job.status.value}")
        version = await session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.id == version_id,
            )
        )
        asset = await session.scalar(
            select(CloudinaryAsset).where(
                CloudinaryAsset.organization_id == organization_id,
                CloudinaryAsset.document_version_id == version_id,
            )
        )
        if version is None or asset is None:
            raise ValueError("Document scan input not found")
        if version.status is not DocumentVersionStatus.SCANNING:
            raise ValueError(f"Document version is {version.status.value}")

        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.error_code = None
        job.error_detail = None
        public_id = asset.public_id
        asset_format = asset.format
        expected_size = version.byte_size
        expected_sha256 = version.sha256
        actor_id = version.created_by_user_id or uuid.UUID(int=0)

    expires_at = int(
        (datetime.now(UTC) + timedelta(seconds=settings.document_download_ttl_seconds)).timestamp()
    )
    download_url = signed_document_download_url(
        settings, public_id=public_id, format=asset_format, expires_at=expires_at
    )
    with tempfile.TemporaryDirectory(prefix="procurex-document-") as directory:
        path = Path(directory) / "quarantined.bin"
        download = await asyncio.to_thread(
            download_verified_asset,
            download_url,
            path,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            maximum_size=settings.document_max_upload_bytes,
            timeout_seconds=settings.document_download_timeout_seconds,
        )
        scan = await asyncio.to_thread(
            scan_with_clamav,
            path,
            command=settings.document_scanner_command,
            timeout_seconds=settings.document_scan_timeout_seconds,
        )

    async with tenant_transaction(organization_id) as session:
        context = RequestContext(
            organization_id=organization_id,
            user_id=actor_id,
            membership_id=uuid.UUID(int=0),
            permissions=frozenset(),
            session=session,
        )
        await record_scan_result(
            context,
            version_id,
            ScanResultCreate(
                scanner=scan.scanner,
                scanner_version=scan.scanner_version,
                status=ScanStatus.CLEAN if scan.clean else ScanStatus.INFECTED,
                result={
                    "byte_size": download.byte_size,
                    "sha256": download.sha256,
                    **({"finding": scan.finding} if scan.finding else {}),
                },
            ),
            actor_type=ActorType.SYSTEM,
        )
    return {
        "status": "clean" if scan.clean else "infected",
        "document_version_id": str(version_id),
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="procurex.document_scan",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def run_document_scan(_: Any, organization_id: str, version_id: str) -> dict[str, object]:
    async def execute_and_close() -> dict[str, object]:
        parsed_organization_id = uuid.UUID(organization_id)
        parsed_version_id = uuid.UUID(version_id)
        try:
            return await _execute_scan(parsed_organization_id, parsed_version_id)
        except Exception as exc:
            await _record_failure(parsed_organization_id, parsed_version_id, exc)
            raise
        finally:
            await close_database()

    return asyncio.run(execute_and_close())
