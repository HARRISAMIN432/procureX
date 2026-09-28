"""Resume the live seed workflow after the sourcing/document setup stage."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.database import close_database
from scripts.seed_and_verify import Api, supplier_api, table_counts


def latest(items: list[dict[str, Any]], field: str = "created_at") -> dict[str, Any]:
    return max(items, key=lambda item: item[field])


def main() -> None:
    state = json.loads(Path("/tmp/procurex-seed-state.json").read_text())
    organization_id = state["organization_id"]
    buyer = Api(
        "http://127.0.0.1:8000",
        headers={
            "X-Organization-ID": organization_id,
            "X-User-ID": state["user_id"],
        },
    )
    run_id = datetime.now(UTC).strftime("%m%d%H%M%S")
    rfq = latest(buyer.call("GET", "/api/v1/rfqs")["items"])
    rfq = buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/amend",
        {
            "expected_version": rfq["version"],
            "submission_deadline": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "terms": rfq["terms"],
            "reason": "Reopen the synthetic verification window",
        },
    )
    requisition = buyer.call("GET", f"/api/v1/requisitions/{rfq['requisition_id']}")
    policy = latest(buyer.call("GET", "/api/v1/approval-policies")["items"])
    suppliers = buyer.call("GET", "/api/v1/suppliers")["items"]
    supplier_by_id = {item["id"]: item for item in suppliers}
    submissions: list[dict[str, Any]] = []
    attachment_version_id: str | None = None
    attachment_document_id: str | None = None

    for invitation in rfq["invitations"]:
        supplier = supplier_by_id[invitation["supplier_id"]]
        portal = supplier_api(organization_id, supplier["contacts"][0]["email"])
        prefix = f"/api/v1/supplier/invitations/{organization_id}/{invitation['id']}"
        view = portal.call("GET", prefix)
        attachments = portal.call("GET", f"{prefix}/documents")
        document_ids: list[str] = []
        if attachments and attachment_version_id is None:
            attachment_version_id = attachments[0]["document_version_id"]
            document_ids = [attachment_version_id]
            documents = buyer.call("GET", "/api/v1/documents")["items"]
            attachment_document_id = next(
                document["id"]
                for document in documents
                if any(version["id"] == attachment_version_id for version in document["versions"])
            )
        submission = portal.call(
            "POST",
            f"{prefix}/submissions",
            {
                "rfq_revision_id": invitation["rfq_revision_id"],
                "currency": "PKR",
                "valid_until": str(date.today() + timedelta(days=30)),
                "delivery_terms": "Delivery within fourteen calendar days",
                "payment_terms": "Net 30 days",
                "notes": "Synthetic supplier portal quotation",
                "document_version_ids": document_ids,
                "lines": [
                    {
                        "rfq_item_id": view["items"][0]["id"],
                        "quantity": "150",
                        "unit_price": str(145000 + len(submissions) * 2500),
                        "tax_amount": "0",
                        "freight_amount": "0",
                        "is_alternative": False,
                        "description": "Synthetic compliant business laptop",
                    }
                ],
            },
        )
        portal.call(
            "POST",
            f"{prefix}/clarifications",
            {"question": "Can delivery be split across two dates?"},
        )
        submissions.append(submission)
        portal.client.close()

    if attachment_version_id is None or attachment_document_id is None:
        raise RuntimeError("Parsed supplier attachment not found")
    document = buyer.call("GET", f"/api/v1/documents/{attachment_document_id}")
    version = next(item for item in document["versions"] if item["id"] == attachment_version_id)
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
                "reason": "Verified against the parsed synthetic source",
            },
        )
    extraction = buyer.call(
        "POST",
        f"/api/v1/extractions/{extraction['id']}/finalize",
        {"expected_revision": extraction["revision"]},
    )

    rfq = buyer.call("GET", f"/api/v1/rfqs/{rfq['id']}")
    rfq = buyer.call(
        "POST",
        f"/api/v1/rfqs/{rfq['id']}/amend",
        {
            "expected_version": rfq["version"],
            "submission_deadline": (datetime.now(UTC) + timedelta(seconds=3)).isoformat(),
            "terms": rfq["terms"],
            "reason": "End synthetic submission period",
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
                            "rationale": "Synthetic offer satisfies this requirement",
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
    analysis = buyer.call("GET", f"/api/v1/evaluation-analysis-runs/{analysis['id']}")
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
    supplier = supplier_by_id[selected_supplier_id]
    portal = supplier_api(organization_id, supplier["contacts"][0]["email"])
    order_path = f"/api/v1/supplier/orders/{organization_id}/{purchase_order['id']}"
    portal.call("GET", order_path)
    purchase_order = portal.call(
        "POST",
        f"{order_path}/acknowledge",
        {
            "expected_version": purchase_order["version"],
            "expected_content_digest": purchase_order["content_digest"],
            "acknowledgement": "accepted",
            "note": "Synthetic supplier acceptance",
        },
    )
    portal.client.close()
    line = purchase_order["current"]["lines"][0]
    receipt = buyer.call(
        "POST",
        f"/api/v1/purchase-orders/{purchase_order['id']}/receipts",
        {
            "expected_po_version": purchase_order["version"],
            "idempotency_key": f"receipt-{run_id}",
            "received_at": datetime.now(UTC).isoformat(),
            "note": "Synthetic inspection receipt",
            "lines": [
                {
                    "purchase_order_line_id": line["id"],
                    "accepted_quantity": "149",
                    "rejected_quantity": "1",
                    "inspection_note": "One synthetic rejected unit",
                }
            ],
        },
    )
    buyer.call(
        "POST",
        f"/api/v1/receipt-lines/{receipt['lines'][0]['id']}/returns",
        {
            "quantity": "1",
            "reason": "Return rejected unit",
            "idempotency_key": f"return-{run_id}",
            "returned_at": datetime.now(UTC).isoformat(),
        },
    )
    subtotal = str(float(line["unit_price"]) * 149)
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
                    "purchase_order_line_id": line["id"],
                    "description": line["description"],
                    "quantity": "149",
                    "unit_price": line["unit_price"],
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
            buyer.call(
                "POST",
                f"/api/v1/match-exceptions/{exception['id']}/resolve",
                {
                    "expected_invoice_version": invoice["version"],
                    "resolution": "Accepted synthetic controlled variance",
                },
            )
            invoice = buyer.call("GET", f"/api/v1/invoices/{invoice['id']}")
    invoice = buyer.call(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/approve-for-export",
        {"expected_invoice_version": invoice["version"]},
    )
    export = buyer.call(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/accounting-exports",
        {
            "expected_invoice_version": invoice["version"],
            "idempotency_key": f"accounting-{run_id}",
        },
    )
    buyer.call(
        "POST",
        f"/api/v1/accounting-exports/{export['id']}/reconcile",
        {
            "expected_version": export["version"],
            "status": "reconciled",
            "note": "Synthetic export reconciled",
        },
    )
    case = buyer.call(
        "POST",
        "/api/v1/commercial/after-sales",
        {
            "purchase_order_id": purchase_order["id"],
            "case_type": "replacement",
            "description": "Replace the synthetic rejected unit.",
            "financial_impact": "0",
        },
    )
    buyer.call(
        "PATCH",
        f"/api/v1/commercial/after-sales/{case['id']}",
        {"status": "resolved", "resolution": "Synthetic replacement accepted."},
    )
    counts, empty = asyncio.run(table_counts(organization_id))
    print(
        json.dumps(
            {
                "organization_id": organization_id,
                "api_checks_passed": len(buyer.checks),
                "database_tables": len(counts),
                "globally_empty_tables": empty,
                "ids": {
                    "requisition": requisition["id"],
                    "rfq": rfq["id"],
                    "evaluation": evaluation["id"],
                    "analysis": analysis["id"],
                    "award": award["id"],
                    "purchase_order": purchase_order["id"],
                    "invoice": invoice["id"],
                    "extraction": extraction["id"],
                },
            },
            indent=2,
        )
    )
    buyer.client.close()
    asyncio.run(close_database())


if __name__ == "__main__":
    main()
