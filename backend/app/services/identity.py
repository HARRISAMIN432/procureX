import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.auth.context import RequestContext
from app.core.config import Settings
from app.core.database import SessionFactory
from app.models.commercial import OrganizationSubscription
from app.models.identity import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationSetting,
    Permission,
    Role,
    RolePermission,
    User,
    UserStatus,
)
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.schemas.identity import (
    MemberInviteCreate,
    MemberRead,
    MembershipUpdate,
    OrganizationBootstrapRequest,
    OrganizationBootstrapResponse,
    OrganizationSettingsWrite,
    OrganizationWorkspaceRead,
    RoleCreate,
    RoleRead,
)

PERMISSION_CATALOG: dict[str, str] = {
    "organization.read": "View organization profile",
    "organization.settings.read": "View organization settings",
    "organization.settings.write": "Create a new organization settings version",
    "organization.members.read": "View organization memberships",
    "organization.members.manage": "Invite, suspend, and assign organization members",
    "documents.read": "View authorized document metadata and content",
    "documents.write": "Upload and manage document versions",
    "documents.scan": "Record trusted malware scan results",
    "documents.process": "Record trusted parser and OCR results",
    "documents.review": "Review and finalize extracted document fields",
    "analysis.read": "View AI analysis runs and evidence",
    "analysis.run": "Start and resume AI analysis runs",
    "audit.read": "View organization audit events",
    "commercial.read": "View plan, entitlements, and usage",
    "organization.data.export": "Export all organization data",
    "organization.lifecycle.manage": "Schedule or cancel organization closure",
    "support.read": "View organization support cases",
    "support.write": "Create support cases",
    "support.manage": "Manage and resolve support cases",
    "operations.after_sales.read": "View returns, replacements, disputes, and credits",
    "operations.after_sales.write": "Create and resolve after-sales cases",
    "requisitions.read": "View requisitions in the organization",
    "requisitions.write": "Create and edit draft requisitions",
    "requisitions.submit": "Submit requisitions for approval",
    "requisitions.cancel": "Cancel permitted requisitions",
    "budgets.read": "View budgets and ledger balances",
    "budgets.manage": "Create budgets and allocations",
    "budgets.reserve": "Reserve available budget during approval",
    "approvals.read": "View approval policies, requests, and decisions",
    "approvals.request": "Request approval for a submitted requisition",
    "approvals.decide": "Approve or reject assigned procurement decisions",
    "approvals.policies.manage": "Create and version approval policies",
    "suppliers.read": "View supplier profiles and qualification records",
    "suppliers.write": "Create and edit supplier profiles",
    "suppliers.qualify": "Assess supplier qualifications and certificates",
    "suppliers.approve": "Approve or suspend suppliers",
    "sourcing.read": "View RFQs, invitations, submissions, and clarifications",
    "sourcing.write": "Create and edit draft RFQs",
    "sourcing.invite": "Select approved suppliers for RFQs",
    "sourcing.publish": "Publish, amend, close, or cancel RFQs",
    "sourcing.submissions.manage": "Record supplier quotation submissions",
    "sourcing.clarifications.write": "Create and answer RFQ clarifications",
    "evaluations.read": "View requirement matrices and evaluated offer comparisons",
    "evaluations.run": "Create deterministic offer evaluation snapshots",
    "allocations.run": "Run and compare deterministic allocation scenarios",
    "awards.read": "View recommendation dossiers and award decisions",
    "awards.write": "Prepare and submit immutable award recommendations",
    "awards.approve": "Approve or reject award recommendations",
    "orders.read": "View purchase orders and delivery history",
    "orders.write": "Create and amend purchase orders",
    "orders.approve": "Authorize material purchase-order amendments",
    "orders.issue": "Issue authorized purchase orders",
    "orders.acknowledge": "Record supplier purchase-order responses",
    "orders.receive": "Record deliveries, inspections, and returns",
    "invoices.read": "View supplier invoices and matching results",
    "invoices.write": "Capture supplier invoices",
    "invoices.match": "Run matching and resolve matching exceptions",
    "invoices.approve": "Approve matched invoices for export",
    "accounting.export": "Export approved invoices to accounting",
    "accounting.reconcile": "Record accounting reconciliation results",
}


class BootstrapDeniedError(ValueError):
    pass


class SlugAlreadyExistsError(ValueError):
    pass


class IdentityConflictError(ValueError):
    pass


class IdentityNotFoundError(ValueError):
    pass


async def list_principal_workspaces(
    *, external_subject: str, email: str | None, email_verified: bool
) -> list[OrganizationWorkspaceRead]:
    """List workspaces for an authenticated identity without opening tenant RLS broadly.

    The security-definer database function exposes only active/invited memberships matching the
    verified provider subject (or an unclaimed invitation matching a verified email address).
    Ordinary domain access still requires selecting one workspace and establishing tenant context.
    """
    async with SessionFactory() as session, session.begin():
        rows = await session.execute(
            text(
                """
                SELECT organization_id, organization_slug, organization_name,
                       organization_status, membership_id, membership_status,
                       is_pending_invitation
                FROM identity_workspaces(:external_subject, :email, :email_verified)
                ORDER BY organization_name, organization_id
                """
            ),
            {
                "external_subject": external_subject,
                "email": email,
                "email_verified": email_verified,
            },
        )
        return [OrganizationWorkspaceRead.model_validate(row._mapping) for row in rows]


def verify_bootstrap_key(settings: Settings, supplied_key: str | None) -> None:
    expected = settings.dev_bootstrap_key.get_secret_value()
    if supplied_key is None or not secrets.compare_digest(supplied_key, expected):
        raise BootstrapDeniedError("Invalid development bootstrap key")


async def bootstrap_organization(
    payload: OrganizationBootstrapRequest,
    *,
    external_subject: str | None = None,
) -> OrganizationBootstrapResponse:
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    role_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with SessionFactory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )
        existing_by_email = await session.scalar(
            select(User).where(func.lower(User.email) == str(payload.admin_email).lower())
        )
        existing_by_subject = (
            await session.scalar(select(User).where(User.external_subject == external_subject))
            if external_subject is not None
            else None
        )
        if (
            existing_by_email is not None
            and existing_by_subject is not None
            and existing_by_email.id != existing_by_subject.id
        ):
            raise IdentityConflictError("Verified identity and email belong to different users")
        existing_user = existing_by_subject or existing_by_email
        if existing_user is None:
            user = User(
                id=user_id,
                email=str(payload.admin_email).lower(),
                display_name=payload.admin_display_name,
                status=UserStatus.ACTIVE,
                external_subject=external_subject,
            )
            session.add(user)
        else:
            user_id = existing_user.id
            if external_subject is not None:
                if existing_user.external_subject not in {None, external_subject}:
                    raise IdentityConflictError("Email is already bound to another identity")
                existing_user.external_subject = external_subject
                existing_user.status = UserStatus.ACTIVE
                existing_user.email = str(payload.admin_email).lower()
                existing_user.display_name = payload.admin_display_name

        session.add(
            Organization(
                id=organization_id,
                slug=payload.organization_slug,
                name=payload.organization_name,
                default_currency=payload.default_currency,
                timezone=payload.timezone,
            )
        )
        try:
            await session.flush()
        except IntegrityError as exc:
            cause = getattr(exc.orig, "__cause__", None)
            constraint_name = getattr(exc.orig, "constraint_name", None) or getattr(
                cause, "constraint_name", None
            )
            if constraint_name == "uq_organizations_slug":
                raise SlugAlreadyExistsError(payload.organization_slug) from exc
            raise
        await session.execute(
            insert(Permission)
            .values(
                [
                    {"code": code, "description": description}
                    for code, description in PERMISSION_CATALOG.items()
                ]
            )
            .on_conflict_do_nothing(index_elements=[Permission.code])
        )
        session.add_all(
            [
                Membership(
                    id=membership_id,
                    organization_id=organization_id,
                    user_id=user_id,
                    status=MembershipStatus.ACTIVE,
                    joined_at=now,
                ),
                Role(
                    id=role_id,
                    organization_id=organization_id,
                    name="Organization administrator",
                    description="Built-in full organization administration role",
                    is_system=True,
                ),
                OrganizationSetting(
                    organization_id=organization_id,
                    version=1,
                    settings={
                        "currency": payload.default_currency,
                        "timezone": payload.timezone,
                        "default_payment_terms_days": 30,
                        "require_po_for_invoice": True,
                    },
                    effective_from=now,
                    created_by_user_id=user_id,
                ),
                OrganizationSubscription(
                    organization_id=organization_id,
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
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                MembershipRole(
                    organization_id=organization_id,
                    membership_id=membership_id,
                    role_id=role_id,
                ),
                *[
                    RolePermission(
                        organization_id=organization_id,
                        role_id=role_id,
                        permission_code=code,
                    )
                    for code in PERMISSION_CATALOG
                ],
            ]
        )
        session.add(
            AuditEvent(
                organization_id=organization_id,
                actor_type=ActorType.USER,
                actor_id=user_id,
                action="organization.created",
                object_type="organization",
                object_id=organization_id,
                object_version=1,
                changes={"slug": payload.organization_slug, "name": payload.organization_name},
            )
        )
        session.add(
            OutboxEvent(
                organization_id=organization_id,
                aggregate_type="organization",
                aggregate_id=organization_id,
                aggregate_version=1,
                event_type="organization.created",
                schema_version=1,
                payload={"organization_id": str(organization_id)},
                actor_id=user_id,
            )
        )

    return OrganizationBootstrapResponse(
        organization_id=organization_id,
        user_id=user_id,
        membership_id=membership_id,
        role_id=role_id,
    )


async def _role_views(context: RequestContext) -> list[RoleRead]:
    roles = list(
        await context.session.scalars(
            select(Role)
            .where(Role.organization_id == context.organization_id)
            .order_by(Role.name, Role.id)
        )
    )
    assignments = list(
        await context.session.execute(
            select(RolePermission.role_id, RolePermission.permission_code)
            .where(RolePermission.organization_id == context.organization_id)
            .order_by(RolePermission.permission_code)
        )
    )
    permissions_by_role: dict[uuid.UUID, list[str]] = {}
    for role_id, permission_code in assignments:
        permissions_by_role.setdefault(role_id, []).append(permission_code)
    return [
        RoleRead(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            permission_codes=permissions_by_role.get(role.id, []),
        )
        for role in roles
    ]


async def list_roles(context: RequestContext) -> list[RoleRead]:
    return await _role_views(context)


async def create_role(context: RequestContext, payload: RoleCreate) -> RoleRead:
    valid_permissions = set(
        await context.session.scalars(
            select(Permission.code).where(Permission.code.in_(payload.permission_codes))
        )
    )
    unknown = sorted(set(payload.permission_codes) - valid_permissions)
    if unknown:
        raise IdentityNotFoundError(f"Unknown permission codes: {', '.join(unknown)}")
    existing = await context.session.scalar(
        select(Role.id).where(
            Role.organization_id == context.organization_id,
            func.lower(Role.name) == payload.name.lower(),
        )
    )
    if existing is not None:
        raise IdentityConflictError("A role with this name already exists")
    role = Role(
        organization_id=context.organization_id,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    context.session.add(role)
    await context.session.flush()
    context.session.add_all(
        [
            RolePermission(
                organization_id=context.organization_id,
                role_id=role.id,
                permission_code=code,
            )
            for code in payload.permission_codes
        ]
    )
    context.session.add(
        AuditEvent(
            organization_id=context.organization_id,
            actor_type=ActorType.USER,
            actor_id=context.user_id,
            action="organization.role_created",
            object_type="role",
            object_id=role.id,
            object_version=1,
            changes={"name": role.name, "permission_codes": sorted(payload.permission_codes)},
        )
    )
    await context.session.flush()
    return RoleRead(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=False,
        permission_codes=sorted(payload.permission_codes),
    )


async def _member_view(context: RequestContext, membership: Membership) -> MemberRead:
    user = await context.session.get(User, membership.user_id)
    assert user is not None
    role_ids = list(
        await context.session.scalars(
            select(MembershipRole.role_id)
            .where(
                MembershipRole.organization_id == context.organization_id,
                MembershipRole.membership_id == membership.id,
            )
            .order_by(MembershipRole.role_id)
        )
    )
    return MemberRead(
        membership_id=membership.id,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=membership.status.value,
        role_ids=role_ids,
        joined_at=membership.joined_at,
    )


async def list_members(context: RequestContext) -> list[MemberRead]:
    memberships = list(
        await context.session.scalars(
            select(Membership)
            .where(Membership.organization_id == context.organization_id)
            .order_by(Membership.created_at, Membership.id)
        )
    )
    return [await _member_view(context, membership) for membership in memberships]


async def _validated_roles(context: RequestContext, role_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    found = list(
        await context.session.scalars(
            select(Role.id).where(
                Role.organization_id == context.organization_id,
                Role.id.in_(role_ids),
            )
        )
    )
    if set(found) != set(role_ids):
        raise IdentityNotFoundError("One or more roles do not exist in this organization")
    return found


async def invite_member(context: RequestContext, payload: MemberInviteCreate) -> MemberRead:
    subscription = await context.session.scalar(
        select(OrganizationSubscription).where(
            OrganizationSubscription.organization_id == context.organization_id
        )
    )
    if subscription is not None:
        seats_used = await context.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == context.organization_id,
                Membership.status.in_([MembershipStatus.ACTIVE, MembershipStatus.INVITED]),
            )
        )
        if int(seats_used or 0) >= subscription.seat_limit:
            raise IdentityConflictError(f"Seat limit reached for the {subscription.plan_code} plan")
    role_ids = await _validated_roles(context, payload.role_ids)
    email = str(payload.email).lower()
    user = await context.session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = User(
            email=email,
            display_name=payload.display_name,
            status=UserStatus.INVITED,
        )
        context.session.add(user)
        await context.session.flush()
    existing = await context.session.scalar(
        select(Membership.id).where(
            Membership.organization_id == context.organization_id,
            Membership.user_id == user.id,
        )
    )
    if existing is not None:
        raise IdentityConflictError("This user already has an organization membership")
    already_active = user.status is UserStatus.ACTIVE and user.external_subject is not None
    membership = Membership(
        organization_id=context.organization_id,
        user_id=user.id,
        status=MembershipStatus.ACTIVE if already_active else MembershipStatus.INVITED,
        invited_by_user_id=context.user_id,
        joined_at=datetime.now(UTC) if already_active else None,
    )
    context.session.add(membership)
    await context.session.flush()
    context.session.add_all(
        [
            MembershipRole(
                organization_id=context.organization_id,
                membership_id=membership.id,
                role_id=role_id,
            )
            for role_id in role_ids
        ]
    )
    context.session.add(
        AuditEvent(
            organization_id=context.organization_id,
            actor_type=ActorType.USER,
            actor_id=context.user_id,
            action="organization.member_invited",
            object_type="membership",
            object_id=membership.id,
            object_version=1,
            changes={"user_id": str(user.id), "role_ids": sorted(map(str, role_ids))},
        )
    )
    await context.session.flush()
    return await _member_view(context, membership)


async def update_membership(
    context: RequestContext, membership_id: uuid.UUID, payload: MembershipUpdate
) -> MemberRead:
    membership = await context.session.scalar(
        select(Membership)
        .where(
            Membership.organization_id == context.organization_id,
            Membership.id == membership_id,
        )
        .with_for_update()
    )
    if membership is None:
        raise IdentityNotFoundError("Membership not found")
    if membership.id == context.membership_id and payload.status in {"suspended", "revoked"}:
        raise IdentityConflictError("You cannot suspend or revoke your own membership")
    if membership.id == context.membership_id and payload.role_ids is not None:
        raise IdentityConflictError("You cannot change your own role assignments")
    target_is_admin = await context.session.scalar(
        select(MembershipRole.membership_id)
        .join(
            Role,
            (Role.organization_id == MembershipRole.organization_id)
            & (Role.id == MembershipRole.role_id),
        )
        .where(
            MembershipRole.organization_id == context.organization_id,
            MembershipRole.membership_id == membership.id,
            Role.is_system.is_(True),
            Role.name == "Organization administrator",
        )
    )
    removes_admin = payload.status in {"suspended", "revoked"}
    if payload.role_ids is not None and target_is_admin is not None:
        admin_role_id = await context.session.scalar(
            select(Role.id).where(
                Role.organization_id == context.organization_id,
                Role.is_system.is_(True),
                Role.name == "Organization administrator",
            )
        )
        removes_admin = admin_role_id not in payload.role_ids
    if target_is_admin is not None and removes_admin:
        other_admin = await context.session.scalar(
            select(Membership.id)
            .join(
                MembershipRole,
                (MembershipRole.organization_id == Membership.organization_id)
                & (MembershipRole.membership_id == Membership.id),
            )
            .join(
                Role,
                (Role.organization_id == MembershipRole.organization_id)
                & (Role.id == MembershipRole.role_id),
            )
            .where(
                Membership.organization_id == context.organization_id,
                Membership.id != membership.id,
                Membership.status == MembershipStatus.ACTIVE,
                Role.is_system.is_(True),
                Role.name == "Organization administrator",
            )
            .limit(1)
        )
        if other_admin is None:
            raise IdentityConflictError("The organization must retain an active administrator")
    if payload.role_ids is not None:
        role_ids = await _validated_roles(context, payload.role_ids)
        await context.session.execute(
            delete(MembershipRole).where(
                MembershipRole.organization_id == context.organization_id,
                MembershipRole.membership_id == membership.id,
            )
        )
        context.session.add_all(
            [
                MembershipRole(
                    organization_id=context.organization_id,
                    membership_id=membership.id,
                    role_id=role_id,
                )
                for role_id in role_ids
            ]
        )
    if payload.status is not None:
        membership.status = MembershipStatus(payload.status)
        if membership.status is MembershipStatus.ACTIVE and membership.joined_at is None:
            membership.joined_at = datetime.now(UTC)
        if membership.status is MembershipStatus.REVOKED:
            membership.revoked_at = datetime.now(UTC)
    context.session.add(
        AuditEvent(
            organization_id=context.organization_id,
            actor_type=ActorType.USER,
            actor_id=context.user_id,
            action="organization.membership_updated",
            object_type="membership",
            object_id=membership.id,
            object_version=1,
            changes=payload.model_dump(mode="json", exclude_none=True),
        )
    )
    await context.session.flush()
    return await _member_view(context, membership)


async def create_organization_settings(
    context: RequestContext,
    payload: OrganizationSettingsWrite,
) -> OrganizationSetting:
    now = datetime.now(UTC)
    effective_from = payload.effective_from or now
    session = context.session

    await session.execute(
        select(Organization.id).where(Organization.id == context.organization_id).with_for_update()
    )
    current = await session.scalar(
        select(OrganizationSetting)
        .where(
            OrganizationSetting.organization_id == context.organization_id,
            OrganizationSetting.effective_to.is_(None),
        )
        .order_by(OrganizationSetting.version.desc())
        .limit(1)
    )
    version = 1 if current is None else current.version + 1
    if current is not None:
        if effective_from <= current.effective_from:
            raise ValueError("effective_from must be later than the current settings version")
        current.effective_to = effective_from

    setting = OrganizationSetting(
        organization_id=context.organization_id,
        version=version,
        settings=payload.settings,
        effective_from=effective_from,
        created_by_user_id=context.user_id,
    )
    session.add(setting)
    await session.flush()

    digest = hashlib.sha256(
        f"{context.organization_id}:{setting.id}:{version}".encode()
    ).hexdigest()
    session.add_all(
        [
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action="organization.settings.created",
                object_type="organization_setting",
                object_id=setting.id,
                object_version=version,
                changes={"version": version, "digest": digest},
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="organization_setting",
                aggregate_id=setting.id,
                aggregate_version=version,
                event_type="organization.settings.created",
                schema_version=1,
                payload={"setting_id": str(setting.id), "version": version},
                actor_id=context.user_id,
            ),
        ]
    )
    return setting
