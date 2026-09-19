import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.auth.context import RequestContext
from app.core.config import Settings
from app.core.database import SessionFactory
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
    OrganizationBootstrapRequest,
    OrganizationBootstrapResponse,
    OrganizationSettingsWrite,
)

PERMISSION_CATALOG: dict[str, str] = {
    "organization.read": "View organization profile",
    "organization.settings.read": "View organization settings",
    "organization.settings.write": "Create a new organization settings version",
    "organization.members.read": "View organization memberships",
    "organization.members.manage": "Invite, suspend, and assign organization members",
    "documents.read": "View authorized document metadata and content",
    "documents.write": "Upload and manage document versions",
    "analysis.read": "View AI analysis runs and evidence",
    "analysis.run": "Start and resume AI analysis runs",
    "audit.read": "View organization audit events",
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
}


class BootstrapDeniedError(ValueError):
    pass


class SlugAlreadyExistsError(ValueError):
    pass


def verify_bootstrap_key(settings: Settings, supplied_key: str | None) -> None:
    expected = settings.dev_bootstrap_key.get_secret_value()
    if supplied_key is None or not secrets.compare_digest(supplied_key, expected):
        raise BootstrapDeniedError("Invalid development bootstrap key")


async def bootstrap_organization(
    payload: OrganizationBootstrapRequest,
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
        existing_user = await session.scalar(
            select(User).where(func.lower(User.email) == str(payload.admin_email).lower())
        )
        if existing_user is None:
            user = User(
                id=user_id,
                email=str(payload.admin_email).lower(),
                display_name=payload.admin_display_name,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
        else:
            user_id = existing_user.id

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
