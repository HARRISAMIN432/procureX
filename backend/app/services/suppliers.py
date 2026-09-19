import uuid
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select

from app.auth.context import RequestContext
from app.models.documents import DocumentVersion
from app.models.identity import Organization
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.models.suppliers import (
    CertificateStatus,
    QualificationStatus,
    Supplier,
    SupplierCertificate,
    SupplierContact,
    SupplierQualification,
    SupplierStatus,
)
from app.schemas.suppliers import (
    CertificateCreate,
    CertificateRead,
    CertificateReview,
    QualificationCreate,
    QualificationDecision,
    QualificationRead,
    SupplierCreate,
    SupplierList,
    SupplierRead,
    SupplierReplace,
    SupplierStatusChange,
)


class SupplierNotFoundError(ValueError):
    pass


class SupplierConflictError(ValueError):
    pass


class SupplierValidationError(ValueError):
    pass


def _record_change(
    context: RequestContext,
    supplier: Supplier,
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
                object_type="supplier",
                object_id=supplier.id,
                object_version=supplier.version,
                changes=changes,
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="supplier",
                aggregate_id=supplier.id,
                aggregate_version=supplier.version,
                event_type=action,
                schema_version=1,
                payload={
                    "supplier_id": str(supplier.id),
                    "version": supplier.version,
                    "status": supplier.status.value,
                },
                actor_id=context.user_id,
            ),
        ]
    )


async def _locked_supplier(context: RequestContext, supplier_id: uuid.UUID) -> Supplier:
    supplier = await context.session.scalar(
        select(Supplier)
        .where(
            Supplier.organization_id == context.organization_id,
            Supplier.id == supplier_id,
        )
        .with_for_update()
    )
    if supplier is None:
        raise SupplierNotFoundError("Supplier not found")
    return supplier


def _check_version(supplier: Supplier, expected_version: int) -> None:
    if supplier.version != expected_version:
        raise SupplierConflictError(
            f"Expected version {expected_version}, current version is {supplier.version}"
        )


async def _replace_contacts(
    context: RequestContext,
    supplier: Supplier,
    payload: SupplierCreate | SupplierReplace,
) -> None:
    await context.session.execute(
        delete(SupplierContact).where(
            SupplierContact.organization_id == context.organization_id,
            SupplierContact.supplier_id == supplier.id,
        )
    )
    context.session.add_all(
        [
            SupplierContact(
                organization_id=context.organization_id,
                supplier_id=supplier.id,
                name=contact.name.strip(),
                email=str(contact.email).lower(),
                phone=contact.phone,
                title=contact.title,
                is_primary=contact.is_primary,
            )
            for contact in payload.contacts
        ]
    )


async def create_supplier(context: RequestContext, payload: SupplierCreate) -> SupplierRead:
    await context.session.scalar(
        select(Organization.id).where(Organization.id == context.organization_id).with_for_update()
    )
    existing = await context.session.scalar(
        select(Supplier.id).where(
            Supplier.organization_id == context.organization_id,
            Supplier.registration_country == payload.registration_country,
            Supplier.registration_number == payload.registration_number,
        )
    )
    if existing is not None:
        raise SupplierConflictError("A supplier with this registration already exists")
    supplier = Supplier(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        legal_name=payload.legal_name,
        trading_name=payload.trading_name,
        registration_country=payload.registration_country,
        registration_number=payload.registration_number,
        tax_identifier=payload.tax_identifier,
        website=payload.website,
        categories=payload.categories,
        capabilities=payload.capabilities,
        status=SupplierStatus.PENDING,
        version=1,
        created_by_user_id=context.user_id,
    )
    context.session.add(supplier)
    await context.session.flush()
    await _replace_contacts(context, supplier, payload)
    _record_change(context, supplier, "supplier.created", {"legal_name": supplier.legal_name})
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def replace_supplier(
    context: RequestContext, supplier_id: uuid.UUID, payload: SupplierReplace
) -> SupplierRead:
    supplier = await _locked_supplier(context, supplier_id)
    _check_version(supplier, payload.expected_version)
    if supplier.status not in {SupplierStatus.PENDING, SupplierStatus.APPROVED}:
        raise SupplierConflictError(f"Cannot edit supplier in {supplier.status.value} state")
    duplicate = await context.session.scalar(
        select(Supplier.id).where(
            Supplier.organization_id == context.organization_id,
            Supplier.registration_country == payload.registration_country,
            Supplier.registration_number == payload.registration_number,
            Supplier.id != supplier.id,
        )
    )
    if duplicate is not None:
        raise SupplierConflictError("A supplier with this registration already exists")

    supplier.legal_name = payload.legal_name
    supplier.trading_name = payload.trading_name
    supplier.registration_country = payload.registration_country
    supplier.registration_number = payload.registration_number
    supplier.tax_identifier = payload.tax_identifier
    supplier.website = payload.website
    supplier.categories = payload.categories
    supplier.capabilities = payload.capabilities
    supplier.version += 1
    if supplier.status is SupplierStatus.APPROVED:
        supplier.status = SupplierStatus.PENDING
        supplier.status_reason = "Material supplier profile changed; reapproval required"
    await _replace_contacts(context, supplier, payload)
    _record_change(context, supplier, "supplier.updated", {"legal_name": supplier.legal_name})
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def create_qualification(
    context: RequestContext, supplier_id: uuid.UUID, payload: QualificationCreate
) -> SupplierRead:
    supplier = await _locked_supplier(context, supplier_id)
    existing = await context.session.scalar(
        select(SupplierQualification.id).where(
            SupplierQualification.organization_id == context.organization_id,
            SupplierQualification.supplier_id == supplier.id,
            SupplierQualification.category == payload.category,
        )
    )
    if existing is not None:
        raise SupplierConflictError("Qualification already exists for this category")
    context.session.add(
        SupplierQualification(
            organization_id=context.organization_id,
            supplier_id=supplier.id,
            category=payload.category.strip(),
            status=QualificationStatus.PENDING,
        )
    )
    supplier.version += 1
    _record_change(
        context, supplier, "supplier.qualification.created", {"category": payload.category}
    )
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def decide_qualification(
    context: RequestContext,
    supplier_id: uuid.UUID,
    qualification_id: uuid.UUID,
    payload: QualificationDecision,
) -> SupplierRead:
    supplier = await _locked_supplier(context, supplier_id)
    qualification = await context.session.scalar(
        select(SupplierQualification)
        .where(
            SupplierQualification.organization_id == context.organization_id,
            SupplierQualification.supplier_id == supplier.id,
            SupplierQualification.id == qualification_id,
        )
        .with_for_update()
    )
    if qualification is None:
        raise SupplierNotFoundError("Qualification not found")
    if (
        payload.status is QualificationStatus.QUALIFIED
        and payload.valid_to is not None
        and payload.valid_to < date.today()
    ):
        raise SupplierValidationError("A qualification cannot be approved with a past expiry")
    qualification.status = payload.status
    qualification.valid_from = payload.valid_from
    qualification.valid_to = payload.valid_to
    qualification.assessment_notes = payload.assessment_notes.strip()
    qualification.assessed_by_user_id = context.user_id
    qualification.assessed_at = datetime.now(UTC)
    supplier.version += 1
    if (
        supplier.status is SupplierStatus.APPROVED
        and payload.status is not QualificationStatus.QUALIFIED
    ):
        supplier.status = SupplierStatus.PENDING
        supplier.status_reason = "Qualification changed; reapproval required"
    _record_change(
        context,
        supplier,
        "supplier.qualification.decided",
        {"qualification_id": str(qualification.id), "status": qualification.status.value},
    )
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def create_certificate(
    context: RequestContext, supplier_id: uuid.UUID, payload: CertificateCreate
) -> SupplierRead:
    supplier = await _locked_supplier(context, supplier_id)
    if payload.qualification_id is not None:
        qualification = await context.session.scalar(
            select(SupplierQualification.id).where(
                SupplierQualification.organization_id == context.organization_id,
                SupplierQualification.supplier_id == supplier.id,
                SupplierQualification.id == payload.qualification_id,
            )
        )
        if qualification is None:
            raise SupplierNotFoundError("Qualification not found")
    if payload.document_version_id is not None:
        document = await context.session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.organization_id == context.organization_id,
                DocumentVersion.id == payload.document_version_id,
            )
        )
        if document is None:
            raise SupplierNotFoundError("Document version not found")
    existing = await context.session.scalar(
        select(SupplierCertificate.id).where(
            SupplierCertificate.organization_id == context.organization_id,
            SupplierCertificate.supplier_id == supplier.id,
            SupplierCertificate.certificate_type == payload.certificate_type,
            SupplierCertificate.certificate_number == payload.certificate_number,
        )
    )
    if existing is not None:
        raise SupplierConflictError("This certificate is already registered")
    certificate = SupplierCertificate(
        organization_id=context.organization_id,
        supplier_id=supplier.id,
        qualification_id=payload.qualification_id,
        certificate_type=payload.certificate_type.strip(),
        certificate_number=payload.certificate_number.strip(),
        issuer=payload.issuer.strip(),
        issued_on=payload.issued_on,
        expires_on=payload.expires_on,
        status=CertificateStatus.PENDING,
        document_version_id=payload.document_version_id,
    )
    context.session.add(certificate)
    supplier.version += 1
    _record_change(
        context,
        supplier,
        "supplier.certificate.created",
        {"certificate_type": certificate.certificate_type},
    )
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def review_certificate(
    context: RequestContext,
    supplier_id: uuid.UUID,
    certificate_id: uuid.UUID,
    payload: CertificateReview,
) -> SupplierRead:
    supplier = await _locked_supplier(context, supplier_id)
    certificate = await context.session.scalar(
        select(SupplierCertificate)
        .where(
            SupplierCertificate.organization_id == context.organization_id,
            SupplierCertificate.supplier_id == supplier.id,
            SupplierCertificate.id == certificate_id,
        )
        .with_for_update()
    )
    if certificate is None:
        raise SupplierNotFoundError("Certificate not found")
    if (
        payload.status is CertificateStatus.VERIFIED
        and certificate.expires_on is not None
        and certificate.expires_on < date.today()
    ):
        raise SupplierValidationError("An expired certificate cannot be verified")
    certificate.status = payload.status
    certificate.reviewed_by_user_id = context.user_id
    certificate.reviewed_at = datetime.now(UTC)
    supplier.version += 1
    _record_change(
        context,
        supplier,
        "supplier.certificate.reviewed",
        {"certificate_id": str(certificate.id), "status": certificate.status.value},
    )
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def approve_supplier(
    context: RequestContext, supplier_id: uuid.UUID, payload: SupplierStatusChange
) -> SupplierRead:
    supplier = await _locked_supplier(context, supplier_id)
    _check_version(supplier, payload.expected_version)
    if supplier.status not in {SupplierStatus.PENDING, SupplierStatus.SUSPENDED}:
        raise SupplierConflictError(f"Cannot approve supplier in {supplier.status.value} state")
    qualified_count = await context.session.scalar(
        select(func.count(SupplierQualification.id)).where(
            SupplierQualification.organization_id == context.organization_id,
            SupplierQualification.supplier_id == supplier.id,
            SupplierQualification.status == QualificationStatus.QUALIFIED,
            SupplierQualification.valid_to >= date.today(),
        )
    )
    if not qualified_count:
        raise SupplierValidationError("At least one current qualification is required")
    supplier.status = SupplierStatus.APPROVED
    supplier.status_reason = payload.reason.strip()
    supplier.version += 1
    _record_change(context, supplier, "supplier.approved", {"reason": supplier.status_reason})
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def suspend_supplier(
    context: RequestContext, supplier_id: uuid.UUID, payload: SupplierStatusChange
) -> SupplierRead:
    supplier = await _locked_supplier(context, supplier_id)
    _check_version(supplier, payload.expected_version)
    if supplier.status is not SupplierStatus.APPROVED:
        raise SupplierConflictError("Only approved suppliers can be suspended")
    supplier.status = SupplierStatus.SUSPENDED
    supplier.status_reason = payload.reason.strip()
    supplier.version += 1
    _record_change(context, supplier, "supplier.suspended", {"reason": supplier.status_reason})
    await context.session.flush()
    return await read_supplier(context, supplier.id)


async def read_supplier(context: RequestContext, supplier_id: uuid.UUID) -> SupplierRead:
    supplier = await context.session.scalar(
        select(Supplier).where(
            Supplier.organization_id == context.organization_id,
            Supplier.id == supplier_id,
        )
    )
    if supplier is None:
        raise SupplierNotFoundError("Supplier not found")
    contacts = list(
        await context.session.scalars(
            select(SupplierContact)
            .where(
                SupplierContact.organization_id == context.organization_id,
                SupplierContact.supplier_id == supplier.id,
            )
            .order_by(SupplierContact.is_primary.desc(), SupplierContact.name)
        )
    )
    qualifications = list(
        await context.session.scalars(
            select(SupplierQualification)
            .where(
                SupplierQualification.organization_id == context.organization_id,
                SupplierQualification.supplier_id == supplier.id,
            )
            .order_by(SupplierQualification.category)
        )
    )
    certificates = list(
        await context.session.scalars(
            select(SupplierCertificate)
            .where(
                SupplierCertificate.organization_id == context.organization_id,
                SupplierCertificate.supplier_id == supplier.id,
            )
            .order_by(SupplierCertificate.certificate_type, SupplierCertificate.certificate_number)
        )
    )
    return SupplierRead(
        id=supplier.id,
        organization_id=supplier.organization_id,
        legal_name=supplier.legal_name,
        trading_name=supplier.trading_name,
        registration_country=supplier.registration_country,
        registration_number=supplier.registration_number,
        tax_identifier=supplier.tax_identifier,
        website=supplier.website,
        categories=supplier.categories,
        capabilities=supplier.capabilities,
        status=supplier.status,
        version=supplier.version,
        status_reason=supplier.status_reason,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
        contacts=[
            {
                "id": contact.id,
                "name": contact.name,
                "email": contact.email,
                "phone": contact.phone,
                "title": contact.title,
                "is_primary": contact.is_primary,
            }
            for contact in contacts
        ],
        qualifications=[
            QualificationRead(
                id=item.id,
                category=item.category,
                status=item.status,
                valid_from=item.valid_from,
                valid_to=item.valid_to,
                assessment_notes=item.assessment_notes,
                assessed_by_user_id=item.assessed_by_user_id,
                assessed_at=item.assessed_at,
            )
            for item in qualifications
        ],
        certificates=[
            CertificateRead(
                id=item.id,
                qualification_id=item.qualification_id,
                certificate_type=item.certificate_type,
                certificate_number=item.certificate_number,
                issuer=item.issuer,
                issued_on=item.issued_on,
                expires_on=item.expires_on,
                status=item.status,
                document_version_id=item.document_version_id,
                reviewed_by_user_id=item.reviewed_by_user_id,
                reviewed_at=item.reviewed_at,
            )
            for item in certificates
        ],
    )


async def list_suppliers(context: RequestContext, limit: int, offset: int) -> SupplierList:
    ids = list(
        await context.session.scalars(
            select(Supplier.id)
            .where(Supplier.organization_id == context.organization_id)
            .order_by(Supplier.legal_name, Supplier.id)
            .limit(limit)
            .offset(offset)
        )
    )
    total = await context.session.scalar(
        select(func.count(Supplier.id)).where(Supplier.organization_id == context.organization_id)
    )
    return SupplierList(
        items=[await read_supplier(context, supplier_id) for supplier_id in ids],
        total=total or 0,
    )
