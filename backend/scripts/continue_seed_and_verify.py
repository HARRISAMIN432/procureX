"""Complete allocation, award, and operations for the latest seeded evaluation."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionFactory, close_database
from scripts.seed_and_verify import Api, supplier_api, table_counts


async def latest_analysis_run(organization_id: str, evaluation_id: str) -> str:
    async with SessionFactory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": organization_id},
        )
        result = await session.execute(
            text(
                "SELECT id FROM analysis_runs "
                "WHERE organization_id = :organization_id AND evaluation_id = :evaluation_id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"organization_id": organization_id, "evaluation_id": evaluation_id},
        )
        return str(result.scalar_one())


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
    evaluations = buyer.call("GET", "/api/v1/evaluations")
    evaluation = max(evaluations, key=lambda item: item["created_at"])
    policies = buyer.call("GET", "/api/v1/approval-policies")["items"]
    policy = max(policies, key=lambda item: item["created_at"])
    suppliers = buyer.call("GET", "/api/v1/suppliers")["items"]
    supplier_by_id = {item["id"]: item for item in suppliers}

    analysis_id = asyncio.run(latest_analysis_run(organization_id, evaluation["id"]))
    analysis = buyer.call("GET", f"/api/v1/evaluation-analysis-runs/{analysis_id}")
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
    portal.call(
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
    purchase_order = buyer.call(
        "GET", f"/api/v1/purchase-orders/{purchase_order['id']}"
    )
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
    export = buyer.call(
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
                    "evaluation": evaluation["id"],
                    "analysis": analysis["id"],
                    "allocation": scenario["id"],
                    "award": award["id"],
                    "purchase_order": purchase_order["id"],
                    "invoice": invoice["id"],
                    "accounting_export": export["id"],
                },
            },
            indent=2,
        )
    )
    buyer.client.close()
    asyncio.run(close_database())


if __name__ == "__main__":
    main()
