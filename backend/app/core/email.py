import html
import json
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import EmailProvider, Settings


class EmailConfigurationError(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RetryableEmailDeliveryError(EmailDeliveryError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, retryable=True)


class Response(Protocol):
    def read(self) -> bytes: ...


class Opener(Protocol):
    def __call__(self, request: Request, *, timeout: float) -> Response: ...


def open_url(request: Request, *, timeout: float) -> Response:
    return cast(Response, urlopen(request, timeout=timeout))  # noqa: S310


@dataclass(frozen=True, slots=True)
class EmailResult:
    provider_message_id: str


class ResendEmailClient:
    endpoint = "https://api.resend.com/emails"

    def __init__(self, settings: Settings, *, opener: Opener = open_url) -> None:
        if settings.email_provider is not EmailProvider.RESEND:
            raise EmailConfigurationError("Transactional email is not enabled")
        if (
            settings.resend_api_key is None
            or not settings.resend_api_key.get_secret_value().strip()
        ):
            raise EmailConfigurationError("Resend API key is not configured")
        self._api_key = settings.resend_api_key.get_secret_value()
        self._from = settings.email_from
        self._reply_to = settings.email_reply_to
        self._timeout = settings.email_timeout_seconds
        self._web_app_url = settings.web_app_url.rstrip("/")
        self._opener = opener

    def send_invitation(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        organization_name: str,
        invited_by_name: str,
        idempotency_key: str,
    ) -> EmailResult:
        sign_in_url = f"{self._web_app_url}/login?invited=1"
        safe_recipient = html.escape(recipient_name)
        safe_organization = html.escape(organization_name)
        safe_inviter = html.escape(invited_by_name)
        subject = f"You have been invited to {organization_name} on ProcureX"
        text_body = (
            f"Hello {recipient_name},\n\n{invited_by_name} invited you to join "
            f"{organization_name} on ProcureX. Sign in using this email address: {sign_in_url}\n\n"
            "If you were not expecting this invitation, you can ignore this message."
        )
        html_body = (
            f"<p>Hello {safe_recipient},</p><p>{safe_inviter} invited you to join "
            f"<strong>{safe_organization}</strong> on ProcureX.</p>"
            f'<p><a href="{html.escape(sign_in_url, quote=True)}">Open ProcureX</a> and sign in '
            "using this email address.</p><p>If you were not expecting this invitation, you can "
            "ignore this message.</p>"
        )
        payload: dict[str, object] = {
            "from": self._from,
            "to": [recipient_email],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
        if self._reply_to:
            payload["reply_to"] = self._reply_to
        request = Request(
            self.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
                "User-Agent": "ProcureX/1.0",
            },
            method="POST",
        )
        try:
            response = self._opener(request, timeout=self._timeout)
            body = json.loads(response.read())
        except HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            code = "provider_temporarily_unavailable" if retryable else "provider_rejected"
            if retryable:
                raise RetryableEmailDeliveryError(
                    code, "Email provider rejected the delivery request"
                ) from exc
            raise EmailDeliveryError(
                code,
                "Email provider rejected the delivery request",
                retryable=False,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RetryableEmailDeliveryError(
                "provider_unavailable",
                "Email provider could not be reached",
            ) from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise RetryableEmailDeliveryError(
                "invalid_provider_response",
                "Email provider returned an invalid response",
            ) from exc
        provider_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(provider_id, str) or not provider_id:
            raise RetryableEmailDeliveryError(
                "invalid_provider_response",
                "Email provider did not return a message ID",
            )
        return EmailResult(provider_message_id=provider_id)
