from collections.abc import Callable
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.models.suppliers import CertificateStatus, QualificationStatus
from app.schemas.suppliers import (
    CertificateCreate,
    CertificateReview,
    QualificationCreate,
    QualificationDecision,
    SupplierCreate,
    SupplierStatusChange,
)


def test_supplier_normalizes_categories_and_contact_names() -> None:
    payload = SupplierCreate(
        legal_name="  Acme Supplies  ",
        registration_country="PK",
        registration_number="  SECP-123  ",
        categories=[" laptops ", "networking", "laptops"],
        contacts=[
            {
                "name": "  Sam Buyer  ",
                "email": "SAM@EXAMPLE.COM",
                "is_primary": True,
            }
        ],
    )

    assert payload.legal_name == "Acme Supplies"
    assert payload.registration_number == "SECP-123"
    assert payload.categories == ["laptops", "networking"]
    assert payload.contacts[0].name == "Sam Buyer"


def test_supplier_rejects_duplicate_contacts() -> None:
    with pytest.raises(ValidationError, match="Contact emails must be unique"):
        SupplierCreate(
            legal_name="Acme Supplies",
            registration_country="PK",
            registration_number="SECP-123",
            contacts=[
                {"name": "Sam", "email": "sam@example.com"},
                {"name": "Samuel", "email": "SAM@example.com"},
            ],
        )


def test_supplier_rejects_multiple_primary_contacts() -> None:
    with pytest.raises(ValidationError, match="Only one contact can be primary"):
        SupplierCreate(
            legal_name="Acme Supplies",
            registration_country="PK",
            registration_number="SECP-123",
            contacts=[
                {"name": "Sam", "email": "sam@example.com", "is_primary": True},
                {"name": "Alex", "email": "alex@example.com", "is_primary": True},
            ],
        )


def test_qualification_requires_a_current_expiry_when_qualified() -> None:
    with pytest.raises(ValidationError, match="require valid_to"):
        QualificationDecision(
            status=QualificationStatus.QUALIFIED,
            assessment_notes="Assessment passed",
        )


def test_qualification_rejects_non_decision_status() -> None:
    with pytest.raises(ValidationError, match="qualified or unqualified"):
        QualificationDecision(
            status=QualificationStatus.PENDING,
            assessment_notes="Still under assessment",
        )


def test_certificate_rejects_inverted_dates() -> None:
    with pytest.raises(ValidationError, match="expires_on"):
        CertificateCreate(
            certificate_type="ISO 9001",
            certificate_number="CERT-1",
            issuer="Certification body",
            issued_on=date.today(),
            expires_on=date.today() - timedelta(days=1),
        )


def test_certificate_review_only_accepts_terminal_review_states() -> None:
    with pytest.raises(ValidationError, match="verified or rejected"):
        CertificateReview(status=CertificateStatus.PENDING)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: QualificationCreate(category="  "), "Category cannot be blank"),
        (
            lambda: SupplierStatusChange(expected_version=1, reason="  "),
            "Reason must contain at least two characters",
        ),
        (
            lambda: CertificateCreate(
                certificate_type="  ",
                certificate_number="CERT-1",
                issuer="Certification body",
            ),
            "Certificate fields cannot be blank",
        ),
    ],
)
def test_supplier_commands_reject_blank_required_text(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        factory()
