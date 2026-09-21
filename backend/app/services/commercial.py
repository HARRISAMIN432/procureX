import enum
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.db.base import Base
from app.models.commercial import (
    AfterSalesCase,
    DataExportRequest,
    OrganizationClosureRequest,
    OrganizationSubscription,
    SupportCase,
)
from app.models.documents import DocumentVersion
from app.models.identity import (
    Membership,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    User,
)
from app.models.operations import PurchaseOrder
from app.models.platform import ActorType, AuditEvent
from app.schemas.commercial import (
    AfterSalesCaseCreate,
    ClosureCreate,
    ExportRead,
    SupportCaseCreate,
)


class CommercialConflictError(ValueError):
    pass


async def subscription_for(context: RequestContext) -> OrganizationSubscription:
    subscription = await context.session.scalar(
        select(OrganizationSubscription).where(
            OrganizationSubscription.organization_id == context.organization_id
        )
    )
    if subscription is None:
        subscription = OrganizationSubscription(
            organization_id=context.organization_id,
            plan_code="community",
            status="active",
            billing_mode="manual",
            seat_limit=5,
            storage_limit_bytes=536_870_912,
            ai_run_limit_monthly=25,
            entitlements={
                "audit_export": True,
                "supplier_portal": False,
                "accounting_export": True,
            },
        )
        context.session.add(subscription)
        await context.session.flush()
    return subscription


def record_event(
    context: RequestContext,
    action: str,
    object_type: str,
    object_id: uuid.UUID,
    changes: dict[str, object],
) -> None:
    context.session.add(
        AuditEvent(
            organization_id=context.organization_id,
            actor_type=ActorType.USER,
            actor_id=context.user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            object_version=1,
            changes=changes,
        )
    )


async def create_support_case(context: RequestContext, payload: SupportCaseCreate) -> SupportCase:
    case = SupportCase(
        organization_id=context.organization_id,
        case_number=f"SUP-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        requester_user_id=context.user_id,
        subject=payload.subject.strip(),
        description=payload.description.strip(),
        priority=payload.priority,
    )
    context.session.add(case)
    await context.session.flush()
    record_event(
        context, "support.case_created", "support_case", case.id, {"priority": case.priority}
    )
    return case


async def schedule_closure(
    context: RequestContext, payload: ClosureCreate
) -> OrganizationClosureRequest:
    existing = await context.session.scalar(
        select(OrganizationClosureRequest).where(
            OrganizationClosureRequest.organization_id == context.organization_id,
            OrganizationClosureRequest.status == "scheduled",
        )
    )
    if existing is not None:
        raise CommercialConflictError("Workspace closure is already scheduled")
    organization = await context.session.get(Organization, context.organization_id)
    assert organization is not None
    organization.status = OrganizationStatus.CLOSING
    closure = OrganizationClosureRequest(
        organization_id=context.organization_id,
        requested_by_user_id=context.user_id,
        reason=payload.reason.strip(),
        scheduled_for=datetime.now(UTC) + timedelta(days=30),
    )
    context.session.add(closure)
    await context.session.flush()
    record_event(
        context,
        "organization.closure_scheduled",
        "organization",
        organization.id,
        {"scheduled_for": closure.scheduled_for.isoformat()},
    )
    return closure


def _json_value(value: object) -> Any:
    if isinstance(value, (datetime, date, uuid.UUID, Decimal, enum.Enum)):
        return str(value.value if isinstance(value, enum.Enum) else value)
    if isinstance(value, bytes):
        return f"<binary:{len(value)} bytes>"
    return value


async def export_organization(context: RequestContext) -> ExportRead:
    data: dict[str, list[dict[str, Any]]] = {}
    for table in Base.metadata.sorted_tables:
        if "organization_id" not in table.c:
            continue
        rows = (
            (
                await context.session.execute(
                    select(table).where(table.c.organization_id == context.organization_id)
                )
            )
            .mappings()
            .all()
        )
        data[table.name] = [{key: _json_value(value) for key, value in row.items()} for row in rows]
    organization = await context.session.scalar(
        select(Organization).where(Organization.id == context.organization_id)
    )
    if organization is not None:
        data["organizations"] = [
            {
                column.key: _json_value(getattr(organization, column.key))
                for column in Organization.__table__.columns
            }
        ]
    users = list(
        await context.session.scalars(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == context.organization_id)
            .order_by(User.id)
        )
    )
    data["users"] = [
        {column.key: _json_value(getattr(user, column.key)) for column in User.__table__.columns}
        for user in users
    ]
    now = datetime.now(UTC)
    request = DataExportRequest(
        organization_id=context.organization_id,
        requested_by_user_id=context.user_id,
        status="completed",
        format="json",
        manifest={name: len(rows) for name, rows in data.items()},
        completed_at=now,
    )
    context.session.add(request)
    await context.session.flush()
    record_event(
        context, "organization.data_exported", "data_export", request.id, {"table_count": len(data)}
    )
    return ExportRead(
        export_id=request.id,
        generated_at=now,
        organization_id=context.organization_id,
        manifest=request.manifest,
        data=data,
    )


async def create_after_sales_case(
    context: RequestContext, payload: AfterSalesCaseCreate
) -> AfterSalesCase:
    purchase_order = await context.session.scalar(
        select(PurchaseOrder.id).where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.id == payload.purchase_order_id,
        )
    )
    if purchase_order is None:
        raise CommercialConflictError("Purchase order not found")
    case = AfterSalesCase(
        organization_id=context.organization_id,
        purchase_order_id=payload.purchase_order_id,
        case_number=f"ASC-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        case_type=payload.case_type,
        description=payload.description.strip(),
        financial_impact=payload.financial_impact,
        created_by_user_id=context.user_id,
    )
    context.session.add(case)
    await context.session.flush()
    record_event(
        context,
        "operations.after_sales_case_created",
        "after_sales_case",
        case.id,
        {"case_type": case.case_type},
    )
    return case


async def usage(context: RequestContext) -> tuple[int, int, int]:
    members = (
        await context.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == context.organization_id,
                Membership.status.in_([MembershipStatus.ACTIVE, MembershipStatus.INVITED]),
            )
        )
        or 0
    )
    stored = (
        await context.session.scalar(
            select(func.coalesce(func.sum(DocumentVersion.byte_size), 0)).where(
                DocumentVersion.organization_id == context.organization_id
            )
        )
        or 0
    )
    cases = (
        await context.session.scalar(
            select(func.count())
            .select_from(SupportCase)
            .where(
                SupportCase.organization_id == context.organization_id,
                SupportCase.status.not_in(["resolved", "closed"]),
            )
        )
        or 0
    )
    return int(members), int(stored), int(cases)
