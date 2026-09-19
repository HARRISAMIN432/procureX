from uuid import UUID

import pytest

from app.core.cloudinary import (
    CloudinaryConfigurationError,
    authenticated_document_upload_options,
    configure_cloudinary,
    signed_document_upload_request,
    verify_document_upload_response,
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


def test_signed_document_upload_is_scoped_and_uses_sha256() -> None:
    settings = Settings(
        cloudinary_cloud_name="procurex-test",
        cloudinary_api_key="api-key",
        cloudinary_api_secret="api-secret",
        cloudinary_folder_prefix="procurex/test",
        _env_file=None,
    )
    request = signed_document_upload_request(
        settings,
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
        timestamp=1_800_000_000,
    )

    assert request["upload_url"].endswith("/procurex-test/raw/upload")
    assert request["parameters"]["type"] == "authenticated"
    assert request["parameters"]["resource_type"] == "raw"
    assert request["parameters"]["overwrite"] is False
    assert len(request["parameters"]["signature"]) == 64


def test_upload_response_signature_is_verified() -> None:
    settings = Settings(cloudinary_api_secret="api-secret", _env_file=None)
    from cloudinary.utils import api_sign_request

    signature = api_sign_request(
        {"public_id": "procurex/test/asset", "version": 123},
        "api-secret",
        signature_version=1,
    )
    assert verify_document_upload_response(
        settings,
        public_id="procurex/test/asset",
        provider_version=123,
        signature=signature,
    )
    assert not verify_document_upload_response(
        settings,
        public_id="procurex/test/other",
        provider_version=123,
        signature=signature,
    )
