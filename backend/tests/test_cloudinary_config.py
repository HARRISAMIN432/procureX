from uuid import UUID

import pytest

from app.core.cloudinary import (
    CloudinaryConfigurationError,
    authenticated_document_upload_options,
    configure_cloudinary,
)
from app.core.config import Settings


def test_document_upload_options_are_private_and_immutable() -> None:
    settings = Settings(cloudinary_folder_prefix="procurex/test", _env_file=None)
    options = authenticated_document_upload_options(
        settings,
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
    )

    assert options["type"] == "authenticated"
    assert options["resource_type"] == "raw"
    assert options["overwrite"] is False
    assert options["public_id"].endswith(
        "/00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000002"
    )


def test_cloudinary_configuration_requires_credentials() -> None:
    with pytest.raises(CloudinaryConfigurationError):
        configure_cloudinary(Settings(_env_file=None))
