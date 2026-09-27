"""Read-only hosted buyer/supplier isolation drill using synthetic test identities.

Supply cookie headers via environment variables; never put them on the command line.
The script prints only status and pass/fail, never cookies or response bodies.
"""

import os
import sys
from urllib.parse import urlparse
from uuid import UUID

import httpx


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def get(client: httpx.Client, path: str, cookie: str) -> httpx.Response:
    return client.get(path, headers={"Cookie": cookie, "Accept": "application/json"})


def expect(label: str, response: httpx.Response, allowed: set[int]) -> None:
    if response.status_code not in allowed:
        raise AssertionError(f"{label}: unexpected HTTP {response.status_code}")
    print(f"PASS {label}: HTTP {response.status_code}")


def run() -> None:
    base = required("PROCUREX_HOSTED_BASE_URL").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"}:
        raise ValueError("Hosted base URL must be an HTTPS origin")
    organization_id = UUID(required("PROCUREX_HOSTED_ORG_ID"))
    rfq_id = UUID(required("PROCUREX_HOSTED_RFQ_ID"))
    invitation_a = UUID(required("PROCUREX_HOSTED_INVITATION_A_ID"))
    invitation_b = UUID(required("PROCUREX_HOSTED_INVITATION_B_ID"))
    supplier_a_id = UUID(required("PROCUREX_HOSTED_SUPPLIER_A_ID"))
    supplier_b_id = UUID(required("PROCUREX_HOSTED_SUPPLIER_B_ID"))
    if invitation_a == invitation_b or supplier_a_id == supplier_b_id:
        raise ValueError("The two invitations and supplier IDs must be distinct")
    cookie_a = required("PROCUREX_HOSTED_SUPPLIER_A_COOKIE")
    cookie_b = required("PROCUREX_HOSTED_SUPPLIER_B_COOKIE")
    buyer_cookie = required("PROCUREX_HOSTED_BUYER_COOKIE")
    if len({cookie_a, cookie_b, buyer_cookie}) != 3:
        raise ValueError("Use three distinct test sessions")
    path_a = f"/api/v1/supplier/invitations/{organization_id}/{invitation_a}"
    path_b = f"/api/v1/supplier/invitations/{organization_id}/{invitation_b}"
    with httpx.Client(base_url=base, timeout=20, follow_redirects=False) as client:
        own_a = get(client, path_a, cookie_a)
        own_b = get(client, path_b, cookie_b)
        expect("supplier A reads own invitation", own_a, {200})
        expect("supplier B reads own invitation", own_b, {200})
        for label, response in (
            ("A cannot read B", get(client, path_b, cookie_a)),
            ("B cannot read A", get(client, path_a, cookie_b)),
            ("buyer is not supplier A", get(client, path_a, buyer_cookie)),
            ("buyer is not supplier B", get(client, path_b, buyer_cookie)),
            ("A cannot read buyer RFQ", get(client, f"/api/v1/rfqs/{rfq_id}", cookie_a)),
            ("B cannot read buyer RFQ", get(client, f"/api/v1/rfqs/{rfq_id}", cookie_b)),
        ):
            expect(label, response, {401, 403, 404, 409})
        expect("buyer reads RFQ", get(client, f"/api/v1/rfqs/{rfq_id}", buyer_cookie), {200})
        for label, response, supplier_id, own_invitation in (
            ("A response redacted", own_a, supplier_a_id, invitation_a),
            ("B response redacted", own_b, supplier_b_id, invitation_b),
        ):
            body = response.json()
            if "invitations" in body or body.get("invitation", {}).get("id") != str(own_invitation):
                raise AssertionError(f"{label}: invitation scope leaked")
            if any(
                item.get("supplier_id") != str(supplier_id) for item in body.get("submissions", [])
            ):
                raise AssertionError(f"{label}: competing submission leaked")
            if any(
                item.get("visibility") == "private"
                and item.get("invitation_id") != str(own_invitation)
                for item in body.get("clarifications", [])
            ):
                raise AssertionError(f"{label}: private clarification leaked")
            print(f"PASS {label}")


if __name__ == "__main__":
    try:
        run()
    except (ValueError, AssertionError, httpx.HTTPError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from None
