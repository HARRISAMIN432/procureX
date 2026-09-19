from typing import Any
from uuid import UUID

import cloudinary  # type: ignore[import-untyped]

from app.core.config import Settings


class CloudinaryConfigurationError(RuntimeError):
    """Raised when Cloudinary is used without complete server credentials."""


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
) -> dict[str, Any]:
    """Return the enforced options for an immutable procurement document upload."""
    folder_prefix = settings.cloudinary_folder_prefix.strip("/")
    public_id = f"{folder_prefix}/{organization_id}/{document_version_id}"
    return {
        "public_id": public_id,
        "resource_type": "raw",
        "type": "authenticated",
        "overwrite": False,
        "unique_filename": False,
        "use_filename": False,
    }
