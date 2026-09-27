from uuid import uuid4

import httpx
import pytest

from scripts import hosted_isolation_probe as probe


def test_probe_requires_distinct_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id, rfq_id, invitation_a, invitation_b, supplier_a, supplier_b = (
        uuid4() for _ in range(6)
    )
    values = {
        "PROCUREX_HOSTED_BASE_URL": "https://example.test",
        "PROCUREX_HOSTED_ORG_ID": str(organization_id),
        "PROCUREX_HOSTED_RFQ_ID": str(rfq_id),
        "PROCUREX_HOSTED_INVITATION_A_ID": str(invitation_a),
        "PROCUREX_HOSTED_INVITATION_B_ID": str(invitation_b),
        "PROCUREX_HOSTED_SUPPLIER_A_ID": str(supplier_a),
        "PROCUREX_HOSTED_SUPPLIER_B_ID": str(supplier_b),
        "PROCUREX_HOSTED_SUPPLIER_A_COOKIE": "session=same",
        "PROCUREX_HOSTED_SUPPLIER_B_COOKIE": "session=same",
        "PROCUREX_HOSTED_BUYER_COOKIE": "session=buyer",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="three distinct"):
        probe.run()


def test_probe_detects_competing_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id, rfq_id, invitation_a, invitation_b, supplier_a, supplier_b = (
        uuid4() for _ in range(6)
    )
    values = {
        "PROCUREX_HOSTED_BASE_URL": "https://example.test",
        "PROCUREX_HOSTED_ORG_ID": str(organization_id),
        "PROCUREX_HOSTED_RFQ_ID": str(rfq_id),
        "PROCUREX_HOSTED_INVITATION_A_ID": str(invitation_a),
        "PROCUREX_HOSTED_INVITATION_B_ID": str(invitation_b),
        "PROCUREX_HOSTED_SUPPLIER_A_ID": str(supplier_a),
        "PROCUREX_HOSTED_SUPPLIER_B_ID": str(supplier_b),
        "PROCUREX_HOSTED_SUPPLIER_A_COOKIE": "session=a",
        "PROCUREX_HOSTED_SUPPLIER_B_COOKIE": "session=b",
        "PROCUREX_HOSTED_BUYER_COOKIE": "session=buyer",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, path: str, *, headers: dict[str, str]) -> httpx.Response:
            cookie = headers["Cookie"]
            if path.endswith(str(rfq_id)):
                return httpx.Response(200 if cookie == "session=buyer" else 403, json={})
            own = (path.endswith(str(invitation_a)) and cookie == "session=a") or (
                path.endswith(str(invitation_b)) and cookie == "session=b"
            )
            if not own:
                return httpx.Response(404, json={})
            invitation_id = invitation_a if cookie == "session=a" else invitation_b
            return httpx.Response(
                200,
                json={
                    "invitation": {"id": str(invitation_id)},
                    "submissions": [{"supplier_id": str(supplier_b)}],
                    "clarifications": [],
                },
            )

    monkeypatch.setattr(probe.httpx, "Client", FakeClient)
    with pytest.raises(AssertionError, match="competing submission leaked"):
        probe.run()
