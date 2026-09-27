from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.auth import supplier as supplier_auth
from app.core.config import AuthMode, Settings
from app.main import create_app
from app.models.identity import OrganizationStatus, UserStatus
from app.models.sourcing import InvitationStatus
from app.models.suppliers import SupplierStatus


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSession:
    def __init__(self, values: list[object]) -> None:
        self.values = iter(values)
        self.statements: list[str] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, statement: object, *_: object) -> None:
        self.statements.append(str(statement))

    async def scalar(self, statement: object) -> object:
        self.statements.append(str(statement))
        return next(self.values)


@pytest.mark.asyncio
async def test_supplier_contact_must_match_exact_invited_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, invitation_id, supplier_id = uuid4(), uuid4(), uuid4()
    invitation = SimpleNamespace(supplier_id=supplier_id, status=InvitationStatus.INVITED)
    db = FakeSession([OrganizationStatus.ACTIVE, invitation, SupplierStatus.APPROVED, None])
    monkeypatch.setattr(supplier_auth, "SessionFactory", lambda: db)

    async def identity(*_: object, **__: object) -> object:
        return SimpleNamespace(email="contact@example.com", email_verified=True)

    monkeypatch.setattr(supplier_auth, "load_auth_session", identity)
    request = Request({"type": "http", "method": "GET", "path": "/"})
    stream = supplier_auth.get_supplier_context(
        request, organization_id, invitation_id, Settings(auth_mode=AuthMode.OIDC, _env_file=None)
    )
    with pytest.raises(HTTPException) as failure:
        await anext(stream)
    assert failure.value.status_code == 404
    assert any(
        "supplier_contacts" in statement and "supplier_id" in statement
        for statement in db.statements
    )


@pytest.mark.asyncio
async def test_supplier_context_has_no_buyer_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id, invitation_id, supplier_id = uuid4(), uuid4(), uuid4()
    invitation = SimpleNamespace(supplier_id=supplier_id, status=InvitationStatus.INVITED)
    user = SimpleNamespace(id=uuid4(), email="contact@example.com", status=UserStatus.ACTIVE)
    db = FakeSession(
        [OrganizationStatus.ACTIVE, invitation, SupplierStatus.APPROVED, uuid4(), user]
    )
    monkeypatch.setattr(supplier_auth, "SessionFactory", lambda: db)

    async def identity(*_: object, **__: object) -> object:
        return SimpleNamespace(
            email="contact@example.com", email_verified=True, external_subject="subject"
        )

    monkeypatch.setattr(supplier_auth, "load_auth_session", identity)
    request = Request({"type": "http", "method": "GET", "path": "/"})
    stream = supplier_auth.get_supplier_context(
        request, organization_id, invitation_id, Settings(auth_mode=AuthMode.OIDC, _env_file=None)
    )
    principal = await anext(stream)
    assert principal.invitation_id == invitation_id
    assert principal.supplier_id == supplier_id
    assert principal.sourcing_context().permissions == frozenset()
    await stream.aclose()


def test_supplier_routes_are_not_available_in_development_header_mode() -> None:
    app = create_app(Settings(auth_mode=AuthMode.DEV_HEADERS, _env_file=None))
    org_id, invitation_id = uuid4(), uuid4()
    with TestClient(app) as client:
        response = client.get(f"/api/v1/supplier/invitations/{org_id}/{invitation_id}")
        old_quote = client.post(f"/api/v1/rfq-invitations/{invitation_id}/submissions")
        old_order_ack = client.post(f"/api/v1/purchase-orders/{uuid4()}/acknowledge")
    assert response.status_code == 404
    assert old_quote.status_code == 404
    assert old_order_ack.status_code == 404


@pytest.mark.asyncio
async def test_supplier_order_requires_contact_for_order_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, order_id, supplier_id = uuid4(), uuid4(), uuid4()
    order = SimpleNamespace(supplier_id=supplier_id)
    db = FakeSession([OrganizationStatus.ACTIVE, order, None])
    monkeypatch.setattr(supplier_auth, "SessionFactory", lambda: db)

    async def identity(*_: object, **__: object) -> object:
        return SimpleNamespace(email="outsider@example.com", email_verified=True)

    monkeypatch.setattr(supplier_auth, "load_auth_session", identity)
    request = Request({"type": "http", "method": "GET", "path": "/"})
    stream = supplier_auth.get_supplier_order_context(
        request, organization_id, order_id, Settings(auth_mode=AuthMode.OIDC, _env_file=None)
    )
    with pytest.raises(HTTPException) as failure:
        await anext(stream)
    assert failure.value.status_code == 404
    assert any(
        "supplier_contacts" in statement and "supplier_id" in statement
        for statement in db.statements
    )
