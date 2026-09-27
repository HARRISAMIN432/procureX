import json
from io import BytesIO
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request
from uuid import uuid4

import pytest

from app.core.config import EmailProvider, Settings
from app.core.email import (
    EmailConfigurationError,
    EmailDeliveryError,
    ResendEmailClient,
    RetryableEmailDeliveryError,
)


class FakeResponse:
    def read(self) -> bytes:
        return b'{"id":"email-provider-id"}'


def test_resend_invitation_is_templated_and_idempotent() -> None:
    captured: dict[str, Any] = {}

    def open_request(request: Request, *, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    settings = Settings(
        email_provider=EmailProvider.RESEND,
        resend_api_key="secret-key",
        email_from="ProcureX <invites@example.com>",
        email_reply_to="support@example.com",
        web_app_url="https://app.example.com",
        _env_file=None,
    )
    result = ResendEmailClient(settings, opener=open_request).send_invitation(
        recipient_email="buyer@example.com",
        recipient_name="Buyer <One>",
        organization_name="Acme & Co",
        invited_by_name="Admin",
        idempotency_key="member-invitation/123",
    )

    request = captured["request"]
    assert isinstance(request, Request)
    payload = json.loads(request.data or b"{}")
    assert result.provider_message_id == "email-provider-id"
    assert request.get_header("Idempotency-key") == "member-invitation/123"
    assert request.get_header("Authorization") == "Bearer secret-key"
    assert payload["to"] == ["buyer@example.com"]
    assert payload["reply_to"] == "support@example.com"
    assert "Buyer &lt;One&gt;" in payload["html"]
    assert "Acme &amp; Co" in payload["html"]
    assert "https://app.example.com/login?invited=1" in payload["html"]


def test_supplier_invitation_email_is_scoped_and_escaped() -> None:
    captured: dict[str, Any] = {}

    def open_request(request: Request, *, timeout: float) -> FakeResponse:
        captured["request"] = request
        return FakeResponse()

    organization_id, invitation_id = uuid4(), uuid4()
    client = ResendEmailClient(
        Settings(
            email_provider=EmailProvider.RESEND,
            resend_api_key="secret-key",
            email_from="ProcureX <invites@example.com>",
            web_app_url="https://app.example.com",
            _env_file=None,
        ),
        opener=open_request,
    )
    result = client.send_supplier_invitation(
        recipient_email="supplier@example.com",
        recipient_name="Contact <One>",
        organization_name="Acme & Co",
        rfq_title="Laptops <urgent>",
        deadline="2026-10-01T00:00:00+00:00",
        organization_id=organization_id,
        invitation_id=invitation_id,
        publication_number=2,
    )
    request = captured["request"]
    assert isinstance(request, Request)
    payload = json.loads(request.data or b"{}")
    assert result.provider_message_id == "email-provider-id"
    assert payload["to"] == ["supplier@example.com"]
    assert "Contact &lt;One&gt;" in payload["html"]
    assert "Acme &amp; Co" in payload["html"]
    assert "Laptops &lt;urgent&gt;" in payload["html"]
    assert f"/supplier/invitations/{organization_id}/{invitation_id}" in payload["html"]
    assert request.get_header("Idempotency-key") == f"supplier-invitation/{invitation_id}/2"
    assert "secret-key" not in payload["text"]


def test_resend_client_requires_explicit_configuration() -> None:
    with pytest.raises(EmailConfigurationError, match="not enabled"):
        ResendEmailClient(Settings(_env_file=None))

    with pytest.raises(EmailConfigurationError, match="API key"):
        ResendEmailClient(
            Settings(email_provider=EmailProvider.RESEND, resend_api_key="", _env_file=None)
        )


@pytest.mark.parametrize(
    ("status", "error_type", "retryable"),
    [
        (400, EmailDeliveryError, False),
        (429, RetryableEmailDeliveryError, True),
        (503, RetryableEmailDeliveryError, True),
    ],
)
def test_resend_classifies_provider_failures(
    status: int, error_type: type[EmailDeliveryError], retryable: bool
) -> None:
    def reject(request: Request, *, timeout: float) -> FakeResponse:
        raise HTTPError(request.full_url, status, "rejected", {}, BytesIO(b"{}"))

    settings = Settings(
        email_provider=EmailProvider.RESEND,
        resend_api_key="secret-key",
        email_from="ProcureX <invites@example.com>",
        _env_file=None,
    )
    with pytest.raises(error_type) as caught:
        ResendEmailClient(settings, opener=reject).send_invitation(
            recipient_email="buyer@example.com",
            recipient_name="Buyer",
            organization_name="Acme",
            invited_by_name="Admin",
            idempotency_key="member-invitation/123",
        )
    assert caught.value.retryable is retryable
