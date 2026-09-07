"""Verifies `SPAPIAuth._sign()` produces a genuinely correct AWS SigV4 signature — not just
that the code runs. Recomputes the expected signature independently, from AWS's publicly
documented algorithm (https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html)
using only stdlib `hashlib`/`hmac`, with no dependency on botocore (what `_sign()` actually
uses) or on `requests_aws4auth` (what the pre-migration code used). A match here means the
new httpx2-based auth wiring signs requests correctly by construction, independent of any
particular signing library's own correctness.
"""

import hashlib
import hmac
import types
import typing

import botocore.credentials
import httpx2

from amzn_selling_partner._auth import SPAPIAuth

ACCESS_KEY = "AKIDEXAMPLE"
SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # noqa # nosec B105
SESSION_TOKEN = "FQoGZXIvYXdzEXAMPLESESSIONTOKEN=="  # noqa # nosec B105
REGION = "us-east-1"
SERVICE = "execute-api"


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _independent_sigv4_authorization(
    *,
    method: str,
    canonical_uri: str,
    headers: typing.Mapping[str, str],
    signed_header_names: typing.List[str],
    body: bytes,
    amz_date: str,
) -> str:
    """Hand-rolled SigV4 signer, deliberately not sharing any code with `_auth.py`."""
    date_stamp = amz_date[:8]
    canonical_headers = "".join(
        f"{name}:{headers[name].strip()}\n" for name in signed_header_names
    )
    signed_headers = ";".join(signed_header_names)
    hashed_payload = hashlib.sha256(body).hexdigest()
    canonical_request = "\n".join(
        [method, canonical_uri, "", canonical_headers, signed_headers, hashed_payload]
    )

    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    k_date = _hmac(("AWS4" + SECRET_KEY).encode("utf-8"), date_stamp)
    k_region = _hmac(k_date, REGION)
    k_service = _hmac(k_region, SERVICE)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return (
        f"AWS4-HMAC-SHA256 Credential={ACCESS_KEY}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def _sign_with_spapi_auth(
    method: str, url: str, headers: typing.Mapping[str, str], body: bytes
) -> httpx2.Request:
    request = httpx2.Request(method, url, content=body, headers=headers)
    credentials = botocore.credentials.ReadOnlyCredentials(ACCESS_KEY, SECRET_KEY, SESSION_TOKEN)
    # Exercise `_sign` in isolation -- it only reads `self._sts.aws_region`, so a minimal
    # stand-in avoids needing real LWA/STS setup for what is purely a signing-math check.
    auth = SPAPIAuth.__new__(SPAPIAuth)
    auth._sts = types.SimpleNamespace(aws_region=REGION)
    auth._sign(request, credentials)
    return request


def _assert_signature_is_correct(
    request: httpx2.Request, *, method: str, canonical_uri: str, body: bytes
) -> None:
    authorization = request.headers["authorization"]
    assert authorization.startswith("AWS4-HMAC-SHA256 Credential=")

    signed_headers = authorization.split("SignedHeaders=")[1].split(",")[0].split(";")
    amz_date = request.headers["x-amz-date"]

    expected = _independent_sigv4_authorization(
        method=method,
        canonical_uri=canonical_uri,
        headers=dict(request.headers.items()),
        signed_header_names=signed_headers,
        body=body,
        amz_date=amz_date,
    )

    assert authorization == expected


def test_sigv4_signature_is_correct_for_post_with_json_body() -> None:
    body = b'{"reportType":"GET_VENDOR_INVENTORY_REPORT","marketplaceIds":["ATVPDKIKX0DER"]}'
    request = _sign_with_spapi_auth(
        "POST",
        "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports",
        {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "x-amz-access-token": "Atza|IwEBILtestaccesstoken",
        },
        body,
    )
    _assert_signature_is_correct(
        request, method="POST", canonical_uri="/reports/2021-06-30/reports", body=body
    )


def test_sigv4_signature_is_correct_for_get_without_body() -> None:
    request = _sign_with_spapi_auth(
        "GET",
        "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports/report-1",
        {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
        b"",
    )
    _assert_signature_is_correct(
        request,
        method="GET",
        canonical_uri="/reports/2021-06-30/reports/report-1",
        body=b"",
    )


def test_sigv4_signature_is_correct_for_vendor_orders_path() -> None:
    request = _sign_with_spapi_auth(
        "GET",
        "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders",
        {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "x-amz-access-token": "Atza|IwEBILtestaccesstoken",
        },
        b"",
    )
    _assert_signature_is_correct(
        request, method="GET", canonical_uri="/vendor/orders/v1/purchaseOrders", body=b""
    )
