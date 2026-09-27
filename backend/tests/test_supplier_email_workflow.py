from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.v1.routes import extractions, sourcing
from app.auth.context import RequestContext
from app.models.sourcing import RfqStatus
from app.schemas.extractions import ManualExtractionCreate
from app.workers import supplier_notifications


@pytest.mark.asyncio
async def test_publish_queues_each_supplier_email(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id, rfq_id = uuid4(), uuid4()
    invitations = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    view = SimpleNamespace(invitations=invitations, publication_number=1)

    async def published(*_: object) -> Any:
        return view

    monkeypatch.setattr(sourcing, "publish_rfq", published)
    background = BackgroundTasks()
    context = cast(RequestContext, SimpleNamespace(organization_id=organization_id))
    result = await sourcing.publish(
        rfq_id, cast(Any, SimpleNamespace(expected_version=1)), context, background
    )
    assert result is view
    assert len(background.tasks) == 2
    assert [task.args for task in background.tasks] == [
        (organization_id, invitations[0].id, 1),
        (organization_id, invitations[1].id, 1),
    ]


class PagesSession:
    def __init__(self, text_value: str) -> None:
        self.text_value = text_value

    async def scalars(self, _: object) -> Any:
        return [SimpleNamespace(page_number=1, text=self.text_value)]


@pytest.mark.asyncio
async def test_manual_extraction_rejects_uncited_source() -> None:
    version_id, parse_id = uuid4(), uuid4()
    payload = ManualExtractionCreate(
        parse_id=parse_id,
        fields=[
            {
                "field_key": "price",
                "label": "Price",
                "value": "500",
                "page_number": 1,
                "quoted_text": "Price 500",
            }
        ],
    )
    context = cast(
        RequestContext,
        SimpleNamespace(organization_id=uuid4(), session=PagesSession("Unrelated page text")),
    )
    with pytest.raises(HTTPException) as failure:
        await extractions.stage_manual_extraction(version_id, payload, context)
    assert failure.value.status_code == 422


@pytest.mark.asyncio
async def test_manual_extraction_stages_only_proposed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version_id, parse_id = uuid4(), uuid4()
    payload = ManualExtractionCreate(
        parse_id=parse_id,
        fields=[
            {
                "field_key": "price",
                "label": "Price",
                "value": "500",
                "page_number": 1,
                "quoted_text": "Price 500",
                "is_critical": True,
            }
        ],
    )
    context = cast(
        RequestContext,
        SimpleNamespace(organization_id=uuid4(), session=PagesSession("Unit Price 500 PKR")),
    )
    captured: dict[str, object] = {}

    async def create(_: object, passed_version: object, result: object) -> Any:
        captured["version"] = passed_version
        captured["result"] = result
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(extractions, "create_extraction", create)
    await extractions.stage_manual_extraction(version_id, payload, context)
    result = cast(Any, captured["result"])
    assert captured["version"] == version_id
    assert result.fields[0].status.value == "proposed"
    assert result.fields[0].is_critical
    assert result.fields[0].anchors[0].quoted_text == "Price 500"


@pytest.mark.asyncio
async def test_supplier_email_task_ignores_stale_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invitation = SimpleNamespace(
        rfq_id=uuid4(), email_publication_number=2, email_status="queued"
    )
    rfq = SimpleNamespace(status=RfqStatus.PUBLISHED, publication_number=2)

    class Session:
        def __init__(self) -> None:
            self.values = iter([invitation, rfq])

        async def scalar(self, _: object) -> Any:
            return next(self.values)

    @asynccontextmanager
    async def transaction(_: object) -> AsyncIterator[Session]:
        yield Session()

    monkeypatch.setattr(supplier_notifications, "tenant_transaction", transaction)
    result = await supplier_notifications._deliver(uuid4(), uuid4(), 1)
    assert result == {"status": "stale_publication"}
    assert invitation.email_status == "queued"


@pytest.mark.asyncio
async def test_supplier_email_task_marks_success_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, invitation_id = uuid4(), uuid4()
    invitation = SimpleNamespace(
        id=invitation_id,
        rfq_id=uuid4(),
        supplier_id=uuid4(),
        email_publication_number=1,
        email_status="queued",
        email_attempts=0,
        email_error_code=None,
    )
    rfq = SimpleNamespace(
        status=RfqStatus.PUBLISHED,
        publication_number=1,
        title="Office supplies",
        submission_deadline=SimpleNamespace(isoformat=lambda: "2026-10-01T00:00:00+00:00"),
    )
    contact = SimpleNamespace(email="contact@example.test", name="Supplier")
    organization = SimpleNamespace(name="Buyer")
    calls: list[dict[str, object]] = []

    class Session:
        def __init__(self) -> None:
            self.values = iter([invitation, rfq, contact, organization])

        async def scalar(self, _: object) -> Any:
            return next(self.values)

        def add(self, _: object) -> None:
            pass

    @asynccontextmanager
    async def transaction(_: object) -> AsyncIterator[Session]:
        yield Session()

    class EmailClient:
        def __init__(self, _: object) -> None:
            pass

        def send_supplier_invitation(self, **kwargs: object) -> Any:
            calls.append(kwargs)
            return SimpleNamespace(provider_message_id="email-123")

    monkeypatch.setattr(supplier_notifications, "tenant_transaction", transaction)
    monkeypatch.setattr(supplier_notifications, "ResendEmailClient", EmailClient)
    first = await supplier_notifications._deliver(organization_id, invitation_id, 1)
    second = await supplier_notifications._deliver(organization_id, invitation_id, 1)
    assert first["status"] == second["status"] == "sent"
    assert len(calls) == 1
    assert calls[0]["recipient_email"] == contact.email
    assert invitation.email_attempts == 1
    assert invitation.email_provider_id == "email-123"
