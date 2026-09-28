"""Seed one synthetic tenant through live ProcureX APIs and verify the full workflow.

Prerequisites:
- buyer API on http://127.0.0.1:8000 in dev_headers mode
- supplier API on http://127.0.0.1:8001 in oidc mode
- /tmp/procurex-seed-state.json created by the dev bootstrap endpoint

The script never removes or updates data outside the bootstrapped tenant.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import secrets
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from docx import Document as WordDocument
from sqlalchemy import select, text

from app.auth.session import digest
from app.core.config import get_settings
from app.core.database import SessionFactory, close_database
from app.models.auth import AuthSession
from app.models.identity import User

BUYER_URL = "http://127.0.0.1:8000"
SUPPLIER_URL = "http://127.0.0.1:8001"
STATE_PATH = Path("/tmp/procurex-seed-state.json")


class Api:
    def __init__(self, base_url: str, **kwargs: Any) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=180, **kwargs)
        self.checks: list[str] = []

    def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: tuple[int, ...] = (200, 201, 204),
    ) -> Any:
        response = self.client.request(method, path, json=payload)
        label = f"{method} {path}"
        if response.status_code not in expected:
            raise RuntimeError(
                f"{label} returned {response.status_code}: {response.text[:2000]}"
            )
        self.checks.append(f"{response.status_code} {label}")
        print(f"PASS {response.status_code} {label}", flush=True)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


async def create_browser_session(
    organization_id: str, email: str, external_subject: str
) -> tuple[str, str]:
    raw_session = secrets.token_urlsafe(48)
    raw_csrf = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    async with SessionFactory() as session, session.begin():
        user = await session.scalar(select(User).where(User.external_subject == external_subject))
        session.add(
            AuthSession(
                token_hash=digest(raw_session),
                csrf_hash=digest(raw_csrf),
                external_subject=external_subject,
                email=email,
                email_verified=True,
                user_id=user.id if user else None,
                selected_organization_id=organization_id,
                expires_at=now + timedelta(hours=2),
                last_seen_at=now,
            )
        )
    return raw_session, raw_csrf


def supplier_api(organization_id: str, email: str) -> Api:
    subject = f"seed-supplier:{email}"
    raw_session, raw_csrf = asyncio.run(
        create_browser_session(organization_id, email, subject)
    )
    settings = get_settings()
    return Api(
        SUPPLIER_URL,
        cookies={
            settings.auth_cookie_name: raw_session,
            settings.auth_csrf_cookie_name: raw_csrf,
        },
        headers={"X-CSRF-Token": raw_csrf},
    )


def docx_fixture() -> bytes:
    document = WordDocument()
    document.add_heading("Supplier quotation", 0)
    document.add_paragraph("Model: PX Business Laptop 14")
    document.add_paragraph("Unit price: PKR 145000.00")
    document.add_paragraph("Warranty: 36 months onsite")
    document.add_paragraph("Delivery: 14 calendar days")
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def upload_supplier_document(
    api: Api, organization_id: str, invitation_id: str, fixture: bytes
) -> tuple[dict[str, Any], dict[str, Any]]:
    prefix = f"/api/v1/supplier/invitations/{organization_id}/{invitation_id}"
    sha256 = hashlib.sha256(fixture).hexdigest()
    intent = api.call(
        "POST",
        f"{prefix}/upload-intents",
        {
            "title": "Synthetic supplier quotation",
            "document_type": "supplier_quote",
            "original_filename": "synthetic-quotation.docx",
            "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "byte_size": len(fixture),
            "sha256": sha256,
        },
    )
    upload = httpx.post(
        intent["upload_url"],
        data={
            key: str(value).lower() if isinstance(value, bool) else str(value)
            for key, value in intent["upload_parameters"].items()
        },
        files={
            "file": (
                "synthetic-quotation.docx",
                fixture,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        timeout=180,
    )
    if upload.status_code not in {200, 201}:
        raise RuntimeError(f"Cloudinary upload failed: {upload.status_code} {upload.text[:1000]}")
    provider = upload.json()
    completed = api.call(
        "POST",
        f"{prefix}/documents/{intent['document_id']}/versions/{intent['document_version_id']}/complete-upload",
        {
            "cloudinary_asset_id": provider["asset_id"],
            "public_id": provider["public_id"],
            "resource_type": provider["resource_type"],
            "delivery_type": provider["type"],
            "provider_version": provider["version"],
            "format": provider.get("format"),
            "byte_size": provider["bytes"],
            "signature": provider["signature"],
        },
    )
    return intent, completed


def run_document_pipeline(organization_id: str, version_id: str) -> None:
    code = """
import asyncio
import sys
from uuid import UUID
from app.core.database import close_database
from app.workers.documents import _execute_parse, _execute_scan

async def main():
    organization_id = UUID(sys.argv[1])
    version_id = UUID(sys.argv[2])
    await _execute_scan(organization_id, version_id)
    await _execute_parse(organization_id, version_id)
    await close_database()

asyncio.run(main())
"""
    command = [sys.executable, "-c", code, organization_id, version_id]
    for attempt in range(6):
        result = subprocess.run(command, check=False, timeout=240)
        if result.returncode == 0:
            return
        if attempt == 5:
            result.check_returncode()
        time.sleep(2)


async def table_counts(organization_id: str) -> tuple[dict[str, int], list[str]]:
    async with SessionFactory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": organization_id},
        )
        names = list(
            await session.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            )
        )
        counts: dict[str, int] = {}
        missing: list[str] = []
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            result = await session.execute(text(f"SELECT count(*) FROM {quoted}"))
            count = int(result.scalar_one())
            counts[name] = count
            if count == 0:
                missing.append(name)
        return counts, missing


def main() -> None:
    bootstrap = json.loads(STATE_PATH.read_text())
    organization_id = bootstrap["organization_id"]
    user_id = bootstrap["user_id"]
    run_id = datetime.now(UTC).strftime("%m%d%H%M%S")
    buyer = Api(
        BUYER_URL,
        headers={"X-Organization-ID": organization_id, "X-User-ID": user_id},
    )

    # Identity and commercial administration.
    buyer.call("GET", "/health/live")
    buyer.call("GET", "/health/ready")
    buyer.call("GET", "/api/v1/organizations/current")
    buyer.call("GET", "/api/v1/organizations/current/membership")
    buyer.call("GET", "/api/v1/organizations/current/settings")
    buyer.call(
        "PUT",
        "/api/v1/organizations/current/settings",
        {
            "settings": {
                "currency": "PKR",
                "timezone": "Asia/Karachi",
                "default_payment_terms_days": 30,
                "require_po_for_invoice": True,
                "seed_run": run_id,
            }
        },
    )
    role = buyer.call(
        "POST",
        "/api/v1/organizations/current/roles",
        {
            "name": f"Seed reviewer {run_id}",
            "description": "Synthetic API verification role",
            "permission_codes": ["organization.read", "requisitions.read", "approvals.read"],
        },
    )
    member = buyer.call(
        "POST",
        "/api/v1/organizations/current/members",
        {
            "email": f"reviewer.{run_id}@example.com",
            "display_name": "Seed Reviewer",
            "role_ids": [role["id"]],
        },
    )
    buyer.call(
        "PATCH",
        f"/api/v1/organizations/current/members/{member['membership_id']}",
        {"status": "active", "role_ids": [role["id"]]},
    )
    support = buyer.call(
        "POST",
        "/api/v1/commercial/support-cases",
        {
            "subject": "Synthetic workflow verification",
            "description": "End-to-end API verification support case for the isolated seed tenant.",
            "priority": "normal",
        },
    )
    buyer.call(
        "PATCH",
        f"/api/v1/commercial/support-cases/{support['id']}",
        {"status": "resolved", "resolution": "Synthetic API verification completed."},
    )
    buyer.call("POST", "/api/v1/commercial/data-export")
    closure = buyer.call(
        "POST",
        "/api/v1/commercial/closure",
        {
            "reason": "Synthetic test of reversible workspace closure request",
            "confirmation": "CLOSE MY WORKSPACE",
        },
    )
    buyer.call("POST", f"/api/v1/commercial/closure/{closure['id']}/cancel")
    buyer.call("GET", "/api/v1/commercial/overview")

    # Budget, requisition, and approval.
    budget = buyer.call(
        "POST",
        "/api/v1/budgets",
        {
            "code": f"IT-{run_id}",
            "name": "Synthetic IT equipment budget",
            "currency": "PKR",
            "period_start": str(date.today()),
            "period_end": str(date.today() + timedelta(days=365)),
            "initial_allocation": "30000000.0000",
        },
    )
    policy = buyer.call(
        "POST",
        "/api/v1/approval-policies",
        {
            "name": f"Synthetic single approval {run_id}",
            "minimum_amount": "0",
            "maximum_amount": "30000000",
            "required_approvals": 1,
            "prohibit_self_approval": False,
            "rules": {"purpose": "seed verification"},
        },
    )
    requisition = buyer.call(
        "POST",
        "/api/v1/requisitions",
        {
            "title": "150 business laptops",
            "justification": (
                "Synthetic competitive purchase used to verify every ProcureX feature."
            ),
            "department": "Information Technology",
            "cost_center": "IT-OPS",
            "currency": "PKR",
            "need_by_date": str(date.today() + timedelta(days=45)),
            "delivery_location": "Karachi",
            "lines": [
                {
                    "line_number": 1,
                    "description": "Business laptop, 14 inch",
                    "quantity": "150",
                    "unit": "each",
                    "estimated_unit_price": "150000",
                    "category": "IT hardware",
                    "specifications": {"ram_gb": 16, "storage_gb": 512},
                    "alternatives_allowed": False,
                }
            ],
            "requirements": [
                {
                    "line_number": 1,
                    "priority": "mandatory",
                    "criterion": "At least 16 GB RAM and 512 GB SSD",
                    "verification_method": "Review supplier quotation",
                    "source": "human",
                    "confirmed": True,
                },
                {
                    "line_number": 1,
                    "priority": "preferred",
                    "criterion": "Three-year onsite warranty",
                    "verification_method": "Review warranty statement",
                    "source": "human",
                    "confirmed": True,
                },
            ],
        },
    )
    requisition = buyer.call(
        "POST",
        f"/api/v1/requisitions/{requisition['id']}/submit",
        {"expected_version": requisition["version"]},
    )
    approval = buyer.call(
        "POST",
        f"/api/v1/requisitions/{requisition['id']}/approval-requests",
        {
            "expected_requisition_version": requisition["version"],
            "budget_id": budget["id"],
            "policy_id": policy["id"],
        },
    )
    approval = buyer.call(
        "POST",
        f"/api/v1/approval-requests/{approval['id']}/approve",
        {"comment": "Approved for synthetic end-to-end verification"},
    )
    requisition = buyer.call("GET", f"/api/v1/requisitions/{requisition['id']}")
    if requisition["status"] != "approved":
        raise RuntimeError(f"Requisition did not approve: {requisition['status']}")

    # Supplier qualification.
    suppliers: list[dict[str, Any]] = []
    for index, name in enumerate(("Alpha Systems", "Beta Technology"), start=1):
        supplier = buyer.call(
            "POST",
            "/api/v1/suppliers",
            {
                "legal_name": f"{name} {run_id} (Private) Limited",
                "trading_name": name,
                "registration_country": "PK",
                "registration_number": f"SEED-{run_id}-{index}",
                "tax_identifier": f"NTN-{run_id}-{index}",
                "website": f"https://supplier{index}.example.com",
                "categories": ["IT hardware"],
                "capabilities": {"annual_capacity": 5000},
                "contacts": [
                    {
                        "name": f"Supplier {index} Contact",
                        "email": f"supplier{index}.{run_id}@example.com",
                        "phone": f"+92-300-00000{index}",
                        "title": "Sales Manager",
                        "is_primary": True,
                    }
                ],
            },
        )
        qualification = buyer.call(
            "POST",
            f"/api/v1/suppliers/{supplier['id']}/qualifications",
            {"category": "IT hardware"},
        )
        qualification_id = qualification["qualifications"][-1]["id"]
        supplier = buyer.call(
            "POST",
            f"/api/v1/suppliers/{supplier['id']}/qualifications/{qualification_id}/decision",
            {
                "status": "qualified",
                "valid_from": str(date.today()),
                "valid_to": str(date.today() + timedelta(days=365)),
                "assessment_notes": "Synthetic due-diligence review passed",
            },
        )
        certificate = buyer.call(
            "POST",
            f"/api/v1/suppliers/{supplier['id']}/certificates",
            {
                "qualification_id": qualification_id,
                "certificate_type": "ISO 9001",
                "certificate_number": f"ISO-{run_id}-{index}",
                "issuer": "Synthetic Certification Authority",
                "issued_on": str(date.today() - timedelta(days=30)),
                "expires_on": str(date.today() + timedelta(days=335)),
            },
        )
        certificate_id = certificate["certificates"][-1]["id"]
        supplier = buyer.call(
            "POST",
            f"/api/v1/suppliers/{supplier['id']}/certificates/{certificate_id}/review",
            {"status": "verified"},
        )
        supplier = buyer.call(
            "POST",
            f"/api/v1/suppliers/{supplier['id']}/approve",
            {"expected_version": supplier["version"], "reason": "Qualified synthetic supplier"},
        )
        suppliers.append(supplier)

    # Sourcing publication and supplier portal access.
    rfq = buyer.call(
        "POST",
        "/api/v1/rfqs",
        {
            "requisition_id": requisition["id"],
            "title": "Competitive RFQ for 150 laptops",
            "submission_deadline": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "terms": {"payment_terms_days": 30, "delivery_city": "Karachi"},
        },
    )
    rfq = buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/invitations",
        {"supplier_ids": [supplier["id"] for supplier in suppliers]},
    )
    rfq = buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/publish",
        {"expected_version": rfq["version"]},
    )
    buyer_question = buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/clarifications",
        {"visibility": "shared", "question": "Confirm that pricing includes delivery to Karachi."},
    )
    buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/clarifications/{buyer_question['id']}/answer",
        {"answer": "Yes, all evaluated prices must include delivery."},
    )

    submissions: list[dict[str, Any]] = []
    attachment_version_id: str | None = None
    for index, supplier in enumerate(suppliers, start=1):
        invitation = next(
            item for item in rfq["invitations"] if item["supplier_id"] == supplier["id"]
        )
        contact_email = supplier["contacts"][0]["email"]
        portal = supplier_api(organization_id, contact_email)
        prefix = f"/api/v1/supplier/invitations/{organization_id}/{invitation['id']}"
        view = portal.call("GET", prefix)
        invitation = portal.call(
            "POST", f"{prefix}/acknowledge", {"expected_rfq_version": view["version"]}
        )
        document_ids: list[str] = []
        if index == 1:
            intent, uploaded = upload_supplier_document(
                portal, organization_id, invitation["id"], docx_fixture()
            )
            attachment_version_id = intent["document_version_id"]
            document_ids = [attachment_version_id]
            run_document_pipeline(organization_id, attachment_version_id)
            uploaded = buyer.call("GET", f"/api/v1/documents/{intent['document_id']}")
            ready_states = {"parsing", "parsed", "extracted", "reviewed"}
            if uploaded["versions"][0]["status"] not in ready_states:
                raise RuntimeError("Uploaded supplier document did not pass quarantine")
            portal.call("GET", f"{prefix}/documents")
            portal.call("GET", f"{prefix}/documents/{attachment_version_id}/download")
        view = portal.call("GET", prefix)
        submission = portal.call(
            "POST",
            f"{prefix}/submissions",
            {
                "rfq_revision_id": invitation["rfq_revision_id"],
                "currency": "PKR",
                "valid_until": str(date.today() + timedelta(days=30)),
                "delivery_terms": f"Delivery in {10 + index * 2} days",
                "payment_terms": "Net 30 days",
                "notes": "Synthetic quotation submitted through supplier portal",
                "document_version_ids": document_ids,
                "lines": [
                    {
                        "rfq_item_id": view["items"][0]["id"],
                        "quantity": "150",
                        "unit_price": str(145000 + index * 2500),
                        "tax_amount": "0",
                        "freight_amount": "0",
                        "is_alternative": False,
                        "description": f"Supplier {index} business laptop",
                    }
                ],
            },
        )
        portal.call(
            "POST",
            f"{prefix}/clarifications",
            {"question": f"Supplier {index}: may delivery be split across two dates?"},
        )
        submissions.append(submission)
        portal.client.close()

    # Manual evidence review over the parsed supplier attachment.
    if attachment_version_id is None:
        raise RuntimeError("Supplier attachment was not created")
    document = buyer.call("GET", f"/api/v1/documents/{intent['document_id']}")
    version = next(item for item in document["versions"] if item["id"] == attachment_version_id)
    if not version["parses"]:
        raise RuntimeError(f"Document parser did not produce a result: {version['status']}")
    parse = next(item for item in version["parses"] if item["status"] == "completed")
    extraction = buyer.call(
        "POST",
        f"/api/v1/documents/versions/{attachment_version_id}/manual-extractions",
        {
            "parse_id": parse["id"],
            "schema_name": "supplier_quote",
            "fields": [
                {
                    "field_key": "unit_price",
                    "label": "Unit price",
                    "value": "145000.00",
                    "page_number": 1,
                    "quoted_text": "Unit price: PKR 145000.00",
                    "is_critical": True,
                },
                {
                    "field_key": "warranty",
                    "label": "Warranty",
                    "value": "36 months onsite",
                    "page_number": 1,
                    "quoted_text": "Warranty: 36 months onsite",
                    "is_critical": False,
                },
            ],
        },
    )
    for field in extraction["fields"]:
        extraction = buyer.call(
            "POST",
            f"/api/v1/extractions/{extraction['id']}/fields/{field['id']}/review",
            {
                "expected_revision": extraction["revision"],
                "action": "verify",
                "reason": "Checked against the parsed synthetic quotation",
            },
        )
    extraction = buyer.call(
        "POST",
        f"/api/v1/extractions/{extraction['id']}/finalize",
        {"expected_revision": extraction["revision"]},
    )

    # Close and evaluate the RFQ after a short deadline amendment.
    rfq = buyer.call("GET", f"/api/v1/rfqs/{rfq['id']}")
    rfq = buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/amend",
        {
            "expected_version": rfq["version"],
            "submission_deadline": (datetime.now(UTC) + timedelta(seconds=3)).isoformat(),
            "terms": rfq["terms"],
            "reason": "Close the synthetic response period after received quotations",
        },
    )
    time.sleep(4)
    rfq = buyer.call(
        "POST", f"/api/v1/rfqs/{rfq['id']}/close", {"expected_version": rfq["version"]}
    )
    evaluation = buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/evaluations",
        {
            "expected_rfq_version": rfq["version"],
            "scoring_policy": {"price_weight": "0.70", "preferred_weight": "0.30"},
            "offers": [
                {
                    "submission_id": submission["id"],
                    "checks": [
                        {
                            "requirement_id": requirement["id"],
                            "outcome": "pass",
                            "rationale": "Synthetic offer satisfies the documented requirement",
                            "evidence_anchor_ids": [],
                        }
                        for requirement in rfq["requirements"]
                    ],
                }
                for submission in submissions
            ],
        },
    )
    analysis = buyer.call(
        "POST", f"/api/v1/evaluations/{evaluation['id']}/analysis-runs"
    )
    buyer.call("GET", f"/api/v1/evaluation-analysis-runs/{analysis['id']}")
    scenario = buyer.call(
        "POST",
        f"/api/v1/evaluations/{evaluation['id']}/allocation-scenarios",
        {
            "name": "Lowest compliant landed cost",
            "expected_evaluation_digest": evaluation["content_digest"],
            "budget_amount": "30000000",
            "maximum_suppliers": 2,
            "allow_split_awards": True,
            "timeout_seconds": 10,
            "fixed_supplier_costs": {},
            "minimum_quantities": [],
        },
    )
    award = buyer.call(
        "POST",
        f"/api/v1/allocation-scenarios/{scenario['id']}/awards",
        {
            "expected_scenario_digest": scenario["content_digest"],
            "recommendation": "Approve the lowest-cost compliant synthetic allocation.",
            "approval_policy_id": policy["id"],
            "analysis_run_id": None,
        },
    )
    award = buyer.call(
        "POST",
        f"/api/v1/awards/{award['id']}/submit",
        {"expected_content_digest": award["content_digest"]},
    )
    award = buyer.call(
        "POST",
        f"/api/v1/awards/{award['id']}/approve",
        {
            "expected_content_digest": award["content_digest"],
            "comment": "Approved synthetic recommendation",
        },
    )

    # Order, receipt, invoice, matching, and accounting export.
    selected_supplier_id = scenario["allocations"][0]["supplier_id"]
    purchase_order = buyer.call(
        "POST",
        f"/api/v1/awards/{award['id']}/purchase-orders",
        {
            "supplier_id": selected_supplier_id,
            "expected_award_digest": award["content_digest"],
            "idempotency_key": f"po-{run_id}",
            "delivery_terms": "Deliver to Karachi within fourteen days",
        },
    )
    purchase_order = buyer.call(
        "POST",
        f"/api/v1/purchase-orders/{purchase_order['id']}/issue",
        {
            "expected_version": purchase_order["version"],
            "expected_content_digest": purchase_order["content_digest"],
        },
    )
    selected_supplier = next(item for item in suppliers if item["id"] == selected_supplier_id)
    order_portal = supplier_api(organization_id, selected_supplier["contacts"][0]["email"])
    order_prefix = f"/api/v1/supplier/orders/{organization_id}/{purchase_order['id']}"
    supplier_order = order_portal.call("GET", order_prefix)
    purchase_order = order_portal.call(
        "POST",
        f"{order_prefix}/acknowledge",
        {
            "expected_version": supplier_order["version"],
            "expected_content_digest": supplier_order["content_digest"],
            "acknowledgement": "accepted",
            "note": "Synthetic supplier accepts the purchase order",
        },
    )
    order_portal.client.close()
    po_line = purchase_order["current"]["lines"][0]
    receipt = buyer.call(
        "POST",
        f"/api/v1/purchase-orders/{purchase_order['id']}/receipts",
        {
            "expected_po_version": purchase_order["version"],
            "idempotency_key": f"receipt-{run_id}",
            "received_at": datetime.now(UTC).isoformat(),
            "note": "Synthetic partial inspection receipt",
            "lines": [
                {
                    "purchase_order_line_id": po_line["id"],
                    "accepted_quantity": "149",
                    "rejected_quantity": "1",
                    "inspection_note": "One unit rejected for synthetic damage scenario",
                }
            ],
        },
    )
    buyer.call(
        "POST",
        f"/api/v1/receipt-lines/{receipt['lines'][0]['id']}/returns",
        {
            "quantity": "1",
            "reason": "Return the rejected synthetic unit",
            "idempotency_key": f"return-{run_id}",
            "returned_at": datetime.now(UTC).isoformat(),
        },
    )
    unit_price = po_line["unit_price"]
    subtotal = str(float(unit_price) * 149)
    invoice = buyer.call(
        "POST",
        f"/api/v1/purchase-orders/{purchase_order['id']}/invoices",
        {
            "supplier_invoice_number": f"INV-{run_id}",
            "invoice_date": str(date.today()),
            "currency": "PKR",
            "subtotal": subtotal,
            "tax_amount": "0",
            "freight_amount": "0",
            "total_amount": subtotal,
            "idempotency_key": f"invoice-{run_id}",
            "lines": [
                {
                    "purchase_order_line_id": po_line["id"],
                    "description": po_line["description"],
                    "quantity": "149",
                    "unit_price": unit_price,
                    "tax_amount": "0",
                    "freight_amount": "0",
                }
            ],
        },
    )
    match = buyer.call(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/match",
        {
            "expected_invoice_version": invoice["version"],
            "mode": "three_way",
            "quantity_tolerance": "0",
            "amount_tolerance": "0.01",
            "percent_tolerance": "0",
            "idempotency_key": f"match-{run_id}",
        },
    )
    invoice = buyer.call("GET", f"/api/v1/invoices/{invoice['id']}")
    for exception in match["exceptions"]:
        if exception["blocking"] and exception["resolved_at"] is None:
            match = buyer.call(
                "POST",
                f"/api/v1/match-exceptions/{exception['id']}/resolve",
                {
                    "expected_invoice_version": invoice["version"],
                    "resolution": "Accepted for the controlled synthetic verification scenario",
                },
            )
            invoice = buyer.call("GET", f"/api/v1/invoices/{invoice['id']}")
    invoice = buyer.call(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/approve-for-export",
        {"expected_invoice_version": invoice["version"]},
    )
    accounting = buyer.call(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/accounting-exports",
        {
            "expected_invoice_version": invoice["version"],
            "idempotency_key": f"accounting-{run_id}",
        },
    )
    buyer.call(
        "POST",
        f"/api/v1/accounting-exports/{accounting['id']}/reconcile",
        {
            "expected_version": accounting["version"],
            "status": "reconciled",
            "note": "Synthetic accounting entry reconciled",
        },
    )
    after_sales = buyer.call(
        "POST",
        "/api/v1/commercial/after-sales",
        {
            "purchase_order_id": purchase_order["id"],
            "case_type": "replacement",
            "description": "Replace the one synthetic unit rejected during inspection.",
            "financial_impact": "0",
        },
    )
    buyer.call(
        "PATCH",
        f"/api/v1/commercial/after-sales/{after_sales['id']}",
        {"status": "resolved", "resolution": "Supplier accepted the replacement request."},
    )

    # Read/list coverage for every primary API feature.
    for path in (
        "/api/v1/organizations/current/roles",
        "/api/v1/organizations/current/members",
        "/api/v1/commercial/support-cases",
        "/api/v1/commercial/after-sales",
        "/api/v1/budgets",
        "/api/v1/approval-policies",
        "/api/v1/approval-requests",
        "/api/v1/requisitions",
        "/api/v1/suppliers",
        "/api/v1/rfqs",
        "/api/v1/documents",
        "/api/v1/evaluations",
        "/api/v1/awards",
        "/api/v1/purchase-orders",
        "/api/v1/invoices",
    ):
        buyer.call("GET", path)

    counts, missing = asyncio.run(table_counts(organization_id))
    report = {
        "organization_id": organization_id,
        "run_id": run_id,
        "api_checks_passed": len(buyer.checks),
        "table_count": len(counts),
        "globally_empty_tables": missing,
        "key_records": {
            "requisition_id": requisition["id"],
            "rfq_id": rfq["id"],
            "evaluation_id": evaluation["id"],
            "award_id": award["id"],
            "purchase_order_id": purchase_order["id"],
            "invoice_id": invoice["id"],
            "document_version_id": attachment_version_id,
            "extraction_id": extraction["id"],
        },
    }
    print(json.dumps(report, indent=2))
    buyer.client.close()
    asyncio.run(close_database())


if __name__ == "__main__":
    main()
