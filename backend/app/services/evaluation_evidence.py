import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import DocumentPage
from app.models.evaluations import Evaluation, OfferEvaluation
from app.models.extractions import (
    EvidenceAnchor,
    ExtractedField,
    ExtractedFieldStatus,
    Extraction,
    ExtractionStatus,
)
from app.models.sourcing import QuoteSubmissionDocument


@dataclass(frozen=True, slots=True)
class AuthorizedEvidence:
    evidence_anchor_id: str
    submission_id: str
    document_version_id: str
    page_number: int
    field_key: str
    field_label: str
    verified_value: object | None
    quoted_text: str

    def as_prompt_record(self) -> dict[str, object]:
        return asdict(self)


async def retrieve_authorized_evidence(
    session: AsyncSession,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    *,
    limit: int,
    max_chars: int,
    anchor_ids: set[uuid.UUID] | None = None,
) -> list[AuthorizedEvidence]:
    """Return only reviewed evidence attached to a submission in this evaluation.

    Tenant, evaluation, quote attachment, completed extraction, and verified-field constraints are
    all enforced in the database query before any relevance/size limiting is applied.
    """
    statement = (
        select(
            EvidenceAnchor.id,
            OfferEvaluation.submission_id,
            EvidenceAnchor.document_version_id,
            DocumentPage.page_number,
            ExtractedField.field_key,
            ExtractedField.label,
            ExtractedField.normalized_value,
            EvidenceAnchor.quoted_text,
            DocumentPage.text,
        )
        .select_from(OfferEvaluation)
        .join(
            Evaluation,
            (Evaluation.organization_id == OfferEvaluation.organization_id)
            & (Evaluation.id == OfferEvaluation.evaluation_id),
        )
        .join(
            QuoteSubmissionDocument,
            (QuoteSubmissionDocument.organization_id == OfferEvaluation.organization_id)
            & (QuoteSubmissionDocument.submission_id == OfferEvaluation.submission_id),
        )
        .join(
            Extraction,
            (Extraction.organization_id == QuoteSubmissionDocument.organization_id)
            & (Extraction.document_version_id == QuoteSubmissionDocument.document_version_id),
        )
        .join(
            ExtractedField,
            (ExtractedField.organization_id == Extraction.organization_id)
            & (ExtractedField.extraction_id == Extraction.id),
        )
        .join(
            EvidenceAnchor,
            (EvidenceAnchor.organization_id == ExtractedField.organization_id)
            & (EvidenceAnchor.extraction_id == ExtractedField.extraction_id)
            & (EvidenceAnchor.field_id == ExtractedField.id),
        )
        .join(
            DocumentPage,
            (DocumentPage.organization_id == EvidenceAnchor.organization_id)
            & (DocumentPage.id == EvidenceAnchor.page_id)
            & (DocumentPage.parse_id == EvidenceAnchor.parse_id),
        )
        .where(
            OfferEvaluation.organization_id == organization_id,
            OfferEvaluation.evaluation_id == evaluation_id,
            Extraction.status == ExtractionStatus.COMPLETED,
            ExtractedField.status == ExtractedFieldStatus.VERIFIED,
        )
        .order_by(OfferEvaluation.submission_id, DocumentPage.page_number, EvidenceAnchor.id)
        .limit(limit)
    )
    if anchor_ids is not None:
        statement = statement.where(EvidenceAnchor.id.in_(anchor_ids))

    rows = (await session.execute(statement)).all()
    results: list[AuthorizedEvidence] = []
    used_chars = 0
    seen: set[uuid.UUID] = set()
    for row in rows:
        if row.id in seen:
            continue
        text = (row.quoted_text or row.text or "").strip()
        if not text:
            continue
        remaining = max_chars - used_chars
        if remaining <= 0:
            break
        text = text[:remaining]
        used_chars += len(text)
        seen.add(row.id)
        results.append(
            AuthorizedEvidence(
                evidence_anchor_id=str(row.id),
                submission_id=str(row.submission_id),
                document_version_id=str(row.document_version_id),
                page_number=row.page_number,
                field_key=row.field_key,
                field_label=row.label,
                verified_value=row.normalized_value,
                quoted_text=text,
            )
        )
    return results
