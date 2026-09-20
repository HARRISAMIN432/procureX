import os
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.context import RequestContext
from app.models.operations import (
    AccountingExportStatus,
    InvoiceStatus,
    MatchMode,
    MatchOutcome,
    PurchaseOrderStatus,
    ReconciliationStatus,
)
from app.schemas.operations import (
    AccountingExportCreate,
    AccountingExportRetry,
    AccountingReconcile,
    InvoiceApprove,
    InvoiceCapture,
    InvoiceMatchCreate,
    PurchaseOrderAcknowledge,
    PurchaseOrderAmend,
    PurchaseOrderCreate,
    ReceiptCreate,
    VersionCommand,
)
from app.services.operations import (
    OperationsConflictError,
    OperationsNotFoundError,
    OperationsValidationError,
    acknowledge_purchase_order,
    amend_purchase_order,
    approve_invoice_for_export,
    authorize_purchase_order_amendment,
    capture_invoice,
    create_purchase_order,
    create_receipt,
    export_invoice,
    issue_purchase_order,
    match_invoice,
    read_purchase_order,
    reconcile_accounting_export,
    retry_accounting_export,
)

TEST_DATABASE_URL = os.getenv("PROCUREX_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="PROCUREX_TEST_DATABASE_URL is required for PostgreSQL tests"
)


class SeedIds(TypedDict):
    organization: UUID
    buyer: UUID
    approver: UUID
    supplier: UUID
    requisition: UUID
    requisition_line: UUID
    rfq: UUID
    rfq_item: UUID
    evaluation: UUID
    scenario: UUID
    policy: UUID
    award: UUID
    award_digest: str


async def seed_approved_award(session: AsyncSession) -> SeedIds:
    generated = {
        name: uuid4()
        for name in (
            "organization",
            "buyer",
            "approver",
            "supplier",
            "requisition",
            "requisition_line",
            "rfq",
            "rfq_item",
            "evaluation",
            "scenario",
            "policy",
            "award",
        )
    }
    ids = SeedIds(**generated, award_digest="a" * 64)
    await session.execute(
        text(
            "INSERT INTO organizations (id, slug, name, status, default_currency, timezone) "
            "VALUES (:id, :slug, 'P7 Test Organization', 'active', 'PKR', 'Asia/Karachi')"
        ),
        {"id": ids["organization"], "slug": f"p7-{str(ids['organization'])[:8]}"},
    )
    for user_key, email in (("buyer", "buyer"), ("approver", "approver")):
        await session.execute(
            text(
                "INSERT INTO users (id, email, display_name, status) "
                "VALUES (:id, :email, :name, 'active')"
            ),
            {
                "id": ids[user_key],
                "email": f"{email}-{ids['organization']}@example.test",
                "name": email.title(),
            },
        )
    await session.execute(
        text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
        {"organization_id": str(ids["organization"])},
    )
    await session.execute(
        text(
            "INSERT INTO suppliers "
            "(id, organization_id, legal_name, registration_country, registration_number, "
            "categories, capabilities, status, version) VALUES "
            "(:id, :org, 'P7 Supplier', 'PK', :registration, '[]', '{}', 'approved', 1)"
        ),
        {
            "id": ids["supplier"],
            "org": ids["organization"],
            "registration": str(ids["supplier"]),
        },
    )
    await session.execute(
        text(
            "INSERT INTO requisitions "
            "(id, organization_id, title, justification, currency, status, version) VALUES "
            "(:id, :org, 'P7 laptops', 'Operational need', 'PKR', 'approved', 1)"
        ),
        {"id": ids["requisition"], "org": ids["organization"]},
    )
    await session.execute(
        text(
            "INSERT INTO requisition_lines "
            "(id, organization_id, requisition_id, line_number, description, quantity, unit, "
            "estimated_unit_price, specifications, alternatives_allowed) VALUES "
            "(:id, :org, :req, 1, 'Business laptop', 10, 'each', 100, '{}', false)"
        ),
        {
            "id": ids["requisition_line"],
            "org": ids["organization"],
            "req": ids["requisition"],
        },
    )
    await session.execute(
        text(
            "INSERT INTO rfqs "
            "(id, organization_id, requisition_id, title, currency, submission_deadline, "
            "terms, status, version, publication_number) VALUES "
            "(:id, :org, :req, 'Laptop RFQ', 'PKR', :deadline, '{}', 'closed', 1, 1)"
        ),
        {
            "id": ids["rfq"],
            "org": ids["organization"],
            "req": ids["requisition"],
            "deadline": datetime.now(UTC) - timedelta(days=1),
        },
    )
    await session.execute(
        text(
            "INSERT INTO rfq_items "
            "(id, organization_id, rfq_id, requisition_line_id, line_number, description, "
            "quantity, unit, specifications, alternatives_allowed) VALUES "
            "(:id, :org, :rfq, :req_line, 1, 'Business laptop', 10, 'each', '{}', false)"
        ),
        {
            "id": ids["rfq_item"],
            "org": ids["organization"],
            "rfq": ids["rfq"],
            "req_line": ids["requisition_line"],
        },
    )
    evaluation_digest = "e" * 64
    scenario_digest = "s" * 64
    award_digest = ids["award_digest"]
    await session.execute(
        text(
            "INSERT INTO evaluations "
            "(id, organization_id, rfq_id, version, source_rfq_version, publication_number, "
            "currency, status, scoring_policy, snapshot, content_digest) VALUES "
            "(:id, :org, :rfq, 1, 1, 1, 'PKR', 'completed', '{}', '{}', :digest)"
        ),
        {
            "id": ids["evaluation"],
            "org": ids["organization"],
            "rfq": ids["rfq"],
            "digest": evaluation_digest,
        },
    )
    await session.execute(
        text(
            "INSERT INTO allocation_scenarios "
            "(id, organization_id, rfq_id, evaluation_id, version, name, "
            "source_evaluation_digest, status, currency, constraints, snapshot, content_digest, "
            "objective_amount, runtime_ms, independently_validated) VALUES "
            "(:id, :org, :rfq, :evaluation, 1, 'Selected', :evaluation_digest, 'feasible', "
            "'PKR', '{}', '{}', :scenario_digest, 1000, 1, true)"
        ),
        {
            "id": ids["scenario"],
            "org": ids["organization"],
            "rfq": ids["rfq"],
            "evaluation": ids["evaluation"],
            "evaluation_digest": evaluation_digest,
            "scenario_digest": scenario_digest,
        },
    )
    await session.execute(
        text(
            "INSERT INTO approval_policies "
            "(id, organization_id, name, version, status, minimum_amount, maximum_amount, "
            "required_approvals, prohibit_self_approval, rules, effective_from) VALUES "
            "(:id, :org, 'P7 award policy', 1, 'active', 0, 100000, 1, true, '{}', :start)"
        ),
        {
            "id": ids["policy"],
            "org": ids["organization"],
            "start": datetime.now(UTC) - timedelta(days=2),
        },
    )
    dossier = {
        "evaluation_digest": evaluation_digest,
        "allocation_digest": scenario_digest,
        "analysis_run_id": None,
        "approval_policy": {"id": str(ids["policy"]), "version": 1},
    }
    snapshot = {
        "allocations": [
            {
                "rfq_item_id": str(ids["rfq_item"]),
                "supplier_id": str(ids["supplier"]),
                "quantity": "10.0000",
                "unit_cost": "100.0000",
            }
        ],
        "submissions": [],
    }
    await session.execute(
        text(
            "INSERT INTO awards "
            "(id, organization_id, rfq_id, evaluation_id, allocation_scenario_id, version, "
            "status, currency, total_amount, recommendation, dossier, snapshot, content_digest, "
            "required_approvals, approval_count, prohibit_self_approval, created_by_user_id, "
            "completed_at) VALUES "
            "(:id, :org, :rfq, :evaluation, :scenario, 1, 'approved', 'PKR', 1000, "
            "'Approved supplier allocation', CAST(:dossier AS jsonb), CAST(:snapshot AS jsonb), "
            ":digest, 1, 1, true, :buyer, :completed)"
        ),
        {
            "id": ids["award"],
            "org": ids["organization"],
            "rfq": ids["rfq"],
            "evaluation": ids["evaluation"],
            "scenario": ids["scenario"],
            "dossier": __import__("json").dumps(dossier),
            "snapshot": __import__("json").dumps(snapshot),
            "digest": award_digest,
            "buyer": ids["buyer"],
            "completed": datetime.now(UTC),
        },
    )
    return ids


@pytest.mark.asyncio
async def test_complete_order_operations_and_failure_paths() -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            ids = await seed_approved_award(session)
            buyer = RequestContext(
                organization_id=ids["organization"],
                user_id=ids["buyer"],
                membership_id=uuid4(),
                permissions=frozenset(),
                session=session,
            )
            approver = RequestContext(
                organization_id=ids["organization"],
                user_id=ids["approver"],
                membership_id=uuid4(),
                permissions=frozenset(),
                session=session,
            )
            create_payload = PurchaseOrderCreate(
                supplier_id=ids["supplier"],
                expected_award_digest=str(ids["award_digest"]),
                idempotency_key="po-create-0001",
            )
            po = await create_purchase_order(
                buyer,
                ids["award"],
                create_payload,
            )
            retried_po = await create_purchase_order(
                buyer,
                ids["award"],
                create_payload,
            )
            assert retried_po.id == po.id
            assert len(po.current.lines) == 1
            with pytest.raises(OperationsConflictError, match="changed PO content"):
                await create_purchase_order(
                    buyer,
                    ids["award"],
                    create_payload.model_copy(update={"delivery_terms": "Changed on retry"}),
                )

            with pytest.raises(OperationsConflictError, match="stale"):
                await create_purchase_order(
                    buyer,
                    ids["award"],
                    create_payload.model_copy(
                        update={
                            "idempotency_key": "po-create-stale",
                            "expected_award_digest": "f" * 64,
                        }
                    ),
                )

            source = po.current.lines[0]
            amended = await amend_purchase_order(
                buyer,
                po.id,
                PurchaseOrderAmend(
                    expected_version=po.version,
                    expected_content_digest=po.content_digest,
                    reason="Increase approved quantity",
                    lines=[
                        {
                            "source_line_id": source.id,
                            "description": source.description,
                            "quantity": "11",
                            "unit": source.unit,
                            "unit_price": source.unit_price,
                        }
                    ],
                ),
            )
            assert amended.status is PurchaseOrderStatus.PENDING_AUTHORIZATION
            with pytest.raises(OperationsValidationError, match="preparer"):
                await authorize_purchase_order_amendment(
                    buyer,
                    po.id,
                    VersionCommand(
                        expected_version=amended.version,
                        expected_content_digest=amended.content_digest,
                    ),
                )
            authorized = await authorize_purchase_order_amendment(
                approver,
                po.id,
                VersionCommand(
                    expected_version=amended.version,
                    expected_content_digest=amended.content_digest,
                ),
            )
            issued = await issue_purchase_order(
                buyer,
                po.id,
                VersionCommand(
                    expected_version=authorized.version,
                    expected_content_digest=authorized.content_digest,
                ),
            )
            acknowledged = await acknowledge_purchase_order(
                approver,
                po.id,
                PurchaseOrderAcknowledge(
                    expected_version=issued.version,
                    expected_content_digest=issued.content_digest,
                    acknowledgement="accepted",
                ),
            )
            assert acknowledged.status is PurchaseOrderStatus.ACKNOWLEDGED
            po_line = acknowledged.current.lines[0]

            partial_payload = ReceiptCreate(
                expected_po_version=acknowledged.version,
                idempotency_key="receipt-partial-0001",
                received_at=datetime.now(UTC),
                lines=[
                    {
                        "purchase_order_line_id": po_line.id,
                        "accepted_quantity": "4",
                        "rejected_quantity": "1",
                    }
                ],
            )
            partial = await create_receipt(buyer, po.id, partial_payload)
            assert (await create_receipt(buyer, po.id, partial_payload)).id == partial.id
            current_po = await read_purchase_order(buyer, po.id)
            assert current_po.status is PurchaseOrderStatus.PARTIALLY_RECEIVED
            with pytest.raises(OperationsValidationError, match="exceed"):
                await create_receipt(
                    buyer,
                    po.id,
                    ReceiptCreate(
                        expected_po_version=current_po.version,
                        idempotency_key="receipt-over-0001",
                        received_at=datetime.now(UTC),
                        lines=[
                            {
                                "purchase_order_line_id": po_line.id,
                                "accepted_quantity": "7",
                                "rejected_quantity": "0",
                            }
                        ],
                    ),
                )

            invoice = await capture_invoice(
                buyer,
                po.id,
                InvoiceCapture(
                    supplier_invoice_number="INV-1001",
                    invoice_date=date.today(),
                    currency="PKR",
                    subtotal="400",
                    tax_amount="0",
                    freight_amount="0",
                    total_amount="400",
                    idempotency_key="invoice-happy-0001",
                    lines=[
                        {
                            "purchase_order_line_id": po_line.id,
                            "description": "Four laptops",
                            "quantity": "4",
                            "unit_price": "100",
                        }
                    ],
                ),
            )
            match_payload = InvoiceMatchCreate(
                expected_invoice_version=invoice.version,
                idempotency_key="match-happy-0001",
            )
            matched = await match_invoice(buyer, invoice.id, match_payload)
            assert matched.outcome is MatchOutcome.MATCHED
            assert (await match_invoice(buyer, invoice.id, match_payload)).id == matched.id
            approved_invoice = await approve_invoice_for_export(
                buyer, invoice.id, InvoiceApprove(expected_invoice_version=invoice.version + 1)
            )
            exported = await export_invoice(
                buyer,
                invoice.id,
                AccountingExportCreate(
                    expected_invoice_version=approved_invoice.version,
                    idempotency_key="export-happy-0001",
                ),
            )
            assert exported.status is AccountingExportStatus.SUCCEEDED
            original_external_id = exported.external_id
            await session.execute(
                text(
                    "UPDATE accounting_exports SET status = 'retry_scheduled', "
                    "external_id = NULL, version = version + 1 WHERE id = :id"
                ),
                {"id": exported.id},
            )
            session.expire_all()
            retried_export = await retry_accounting_export(
                buyer,
                exported.id,
                AccountingExportRetry(expected_version=exported.version + 1),
            )
            assert retried_export.external_id == original_external_id
            assert retried_export.attempt_count == 2
            reconciled = await reconcile_accounting_export(
                buyer,
                exported.id,
                AccountingReconcile(
                    expected_version=retried_export.version,
                    status=ReconciliationStatus.RECONCILED,
                ),
            )
            assert reconciled.status is AccountingExportStatus.RECONCILED

            duplicate = await capture_invoice(
                buyer,
                po.id,
                InvoiceCapture(
                    supplier_invoice_number=" inv / 1001 ",
                    invoice_date=date.today(),
                    currency="PKR",
                    subtotal="100",
                    tax_amount="0",
                    freight_amount="0",
                    total_amount="100",
                    idempotency_key="invoice-duplicate-0001",
                    lines=[
                        {
                            "purchase_order_line_id": po_line.id,
                            "description": "Duplicate",
                            "quantity": "1",
                            "unit_price": "100",
                        }
                    ],
                ),
            )
            assert duplicate.status is InvoiceStatus.DUPLICATE_SUSPECTED
            duplicate_match = await match_invoice(
                buyer,
                duplicate.id,
                InvoiceMatchCreate(
                    expected_invoice_version=duplicate.version,
                    mode=MatchMode.TWO_WAY,
                    idempotency_key="match-duplicate-0001",
                ),
            )
            assert duplicate_match.outcome is MatchOutcome.MISMATCH
            assert "duplicate_invoice" in {item.kind.value for item in duplicate_match.exceptions}

            overbilled = await capture_invoice(
                buyer,
                po.id,
                InvoiceCapture(
                    supplier_invoice_number="INV-OVER-1",
                    invoice_date=date.today(),
                    currency="PKR",
                    subtotal="606",
                    tax_amount="10",
                    freight_amount="5",
                    total_amount="621",
                    idempotency_key="invoice-overbill-0001",
                    lines=[
                        {
                            "purchase_order_line_id": po_line.id,
                            "description": "Overbilled laptops",
                            "quantity": "6",
                            "unit_price": "101",
                            "tax_amount": "10",
                            "freight_amount": "5",
                        }
                    ],
                ),
            )
            mismatch = await match_invoice(
                buyer,
                overbilled.id,
                InvoiceMatchCreate(
                    expected_invoice_version=overbilled.version,
                    idempotency_key="match-overbill-0001",
                ),
            )
            assert mismatch.outcome is MatchOutcome.MISMATCH
            assert {item.kind.value for item in mismatch.exceptions} >= {
                "quantity",
                "price",
                "tax",
                "freight",
            }
            with pytest.raises(OperationsConflictError, match="stale"):
                await match_invoice(
                    buyer,
                    overbilled.id,
                    InvoiceMatchCreate(
                        expected_invoice_version=1,
                        idempotency_key="match-stale-0001",
                    ),
                )

            outsider = RequestContext(
                organization_id=uuid4(),
                user_id=ids["buyer"],
                membership_id=uuid4(),
                permissions=frozenset(),
                session=session,
            )
            await session.execute(
                text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
                {"organization_id": str(outsider.organization_id)},
            )
            with pytest.raises(OperationsNotFoundError):
                await read_purchase_order(outsider, po.id)
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
