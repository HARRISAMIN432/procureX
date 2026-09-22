import secrets
import time
from typing import Any
from uuid import UUID

import cloudinary  # type: ignore[import-untyped]
from cloudinary.utils import (  # type: ignore[import-untyped]
    SIGNATURE_SHA1,
    SIGNATURE_SHA256,
    api_sign_request,
    private_download_url,
)

from app.core.config import Settings


class CloudinaryConfigurationError(RuntimeError):
    """Raised when Cloudinary is used without complete server credentials."""


DOCUMENT_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/jpeg": ".jpeg",
    "image/png": ".png",
}


def configure_cloudinary(settings: Settings) -> None:
    """Configure the server-side SDK without exposing secret values."""
    if (
        settings.cloudinary_cloud_name is None
        or settings.cloudinary_api_key is None
        or settings.cloudinary_api_secret is None
    ):
        raise CloudinaryConfigurationError("Cloudinary server credentials are incomplete")

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key.get_secret_value(),
        api_secret=settings.cloudinary_api_secret.get_secret_value(),
        secure=True,
    )


def authenticated_document_upload_options(
    settings: Settings,
    organization_id: UUID,
    document_version_id: UUID,
    *,
    media_type: str | None = None,
) -> dict[str, Any]:
    """Return the enforced options for an immutable procurement document upload."""
    folder_prefix = settings.cloudinary_folder_prefix.strip("/")
    extension = DOCUMENT_EXTENSIONS.get(media_type or "", "")
    public_id = f"{folder_prefix}/{organization_id}/{document_version_id}{extension}"
    return {
        "public_id": public_id,
        "resource_type": "raw",
        "type": "authenticated",
        "overwrite": False,
        "unique_filename": False,
        "use_filename": False,
    }


def signed_document_upload_request(
    settings: Settings,
    organization_id: UUID,
    document_version_id: UUID,
    *,
    media_type: str | None = None,
    timestamp: int | None = None,
) -> dict[str, Any]:
    """Create a narrowly scoped signed request for a quarantined raw asset."""
    configure_cloudinary(settings)
    assert settings.cloudinary_api_key is not None
    assert settings.cloudinary_api_secret is not None
    assert settings.cloudinary_cloud_name is not None
    issued_at = int(time.time()) if timestamp is None else timestamp
    options = authenticated_document_upload_options(
        settings,
        organization_id,
        document_version_id,
        media_type=media_type,
    )
    signed_parameters = {
        "public_id": options["public_id"],
        "type": options["type"],
        # Match Cloudinary's canonical wire encoding. Browser FormData would otherwise stringify
        # Python booleans as "False", producing a signature different from the provider's "0".
        "overwrite": "0",
        "unique_filename": "0",
        "use_filename": "0",
        "timestamp": issued_at,
    }
    signature = api_sign_request(
        signed_parameters,
        settings.cloudinary_api_secret.get_secret_value(),
        algorithm=SIGNATURE_SHA256,
        signature_version=2,
    )
    return {
        "upload_url": (
            f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/raw/upload"
        ),
        "parameters": {
            **signed_parameters,
            "resource_type": options["resource_type"],
            "api_key": settings.cloudinary_api_key.get_secret_value(),
            "signature": signature,
        },
    }


def verify_document_upload_response(
    settings: Settings,
    *,
    public_id: str,
    provider_version: int,
    signature: str,
) -> bool:
    """Verify the signature returned by Cloudinary after a successful upload."""
    if settings.cloudinary_api_secret is None:
        raise CloudinaryConfigurationError("Cloudinary server credentials are incomplete")
    expected = api_sign_request(
        {"public_id": public_id, "version": provider_version},
        settings.cloudinary_api_secret.get_secret_value(),
        algorithm=SIGNATURE_SHA1,
        signature_version=1,
    )
    return secrets.compare_digest(signature, expected)


def signed_document_download_url(
    settings: Settings,
    *,
    public_id: str,
    format: str | None,
    expires_at: int,
) -> str:
    """Create a short-lived URL for an already-authorized authenticated raw asset."""
    configure_cloudinary(settings)
    return str(
        private_download_url(
            public_id,
            format or "",
            resource_type="raw",
            type="authenticated",
            attachment=True,
            expires_at=expires_at,
        )
    )
