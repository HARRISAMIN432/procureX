import re

from fastapi.testclient import TestClient

from app.core.config import AuthMode, Environment, Settings
from app.main import create_app


def production_settings() -> Settings:
    return Settings(
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.OIDC,
        oidc_issuer="https://identity.example.com",
        oidc_audience="procurex-api",
        cloudinary_cloud_name="procurex",
        cloudinary_api_key="key",
        cloudinary_api_secret="secret",
        gemini_api_key="model-key",
        allowed_hosts=["api.procurex.example"],
        cors_allowed_origins=["https://app.procurex.example"],
        _env_file=None,
    )


def test_security_headers_and_valid_request_id_are_returned() -> None:
    application = create_app(Settings(_env_file=None))
    with TestClient(application) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "pilot-check-42"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "pilot-check-42"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


def test_invalid_request_id_is_replaced() -> None:
    application = create_app(Settings(_env_file=None))
    with TestClient(application) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "invalid request id"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "invalid request id"
    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["x-request-id"])


def test_untrusted_host_is_rejected_with_security_headers() -> None:
    application = create_app(Settings(allowed_hosts=["api.procurex.test"], _env_file=None))
    with TestClient(application, base_url="http://attacker.example") as client:
        response = client.get("/health/live")

    assert response.status_code == 400
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "x-request-id" in response.headers


def test_cors_allows_only_configured_origin() -> None:
    application = create_app(
        Settings(cors_allowed_origins=["https://app.procurex.test"], _env_file=None)
    )
    with TestClient(application) as client:
        allowed = client.options(
            "/health/live",
            headers={
                "Origin": "https://app.procurex.test",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,X-Organization-ID,X-User-ID",
            },
        )
        denied = client.options(
            "/health/live",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.procurex.test"
    assert "X-Organization-ID" in allowed.headers["access-control-allow-headers"]
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_production_enables_hsts_and_disables_api_docs() -> None:
    application = create_app(production_settings())
    with TestClient(application, base_url="https://api.procurex.example") as client:
        health = client.get("/health/live")
        docs = client.get("/docs")
        schema = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.headers["strict-transport-security"].startswith("max-age=31536000")
    assert docs.status_code == 404
    assert schema.status_code == 404
