"""A MockTransport handler emulating the LWA token endpoint, the Tokens API and
a few Orders/Reports/Feeds operations for the plugin tests."""

from __future__ import annotations

import gzip
import json

import httpx2

TOKEN_URL_PATH = "/auth/o2/token"
ORDER = {
    "AmazonOrderId": "902-1",
    "PurchaseDate": "2020-01-01T00:00:00Z",
    "LastUpdateDate": "2020-01-01T00:00:00Z",
    "OrderStatus": "Shipped",
}


class AmazonMock:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.token_calls = 0
        self.rdt_calls = 0
        self.token_ttl = 3600
        self.fail_token = False
        self.report_bytes = b"col1\tcol2\nv1\tv2\n"

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path
        if path == TOKEN_URL_PATH:
            self.token_calls += 1
            if self.fail_token:
                return httpx2.Response(400, json={"error": "invalid_grant", "error_description": "bad"})
            form = dict(p.split("=", 1) for p in request.content.decode().split("&"))
            kind = "cc" if form.get("grant_type") == "client_credentials" else "rt"
            return httpx2.Response(
                200, json={"access_token": f"Atza|{kind}|{self.token_calls}", "expires_in": self.token_ttl, "token_type": "bearer"}
            )
        if path == "/tokens/2021-03-01/restrictedDataToken":
            self.rdt_calls += 1
            body = json.loads(request.content)
            res = body["restrictedResources"][0]
            return httpx2.Response(
                200,
                json={
                    "restrictedDataToken": f"RDT|{res['method']}|{res['path']}|{','.join(res.get('dataElements', []))}",
                    "expiresIn": 3600,
                },
            )
        if path == "/orders/v0/orders":
            token = request.url.params.get("NextToken")
            if token == "n2":
                return httpx2.Response(200, json={"payload": {"Orders": [dict(ORDER, AmazonOrderId="902-2")], "NextToken": "n3"}})
            if token == "n3":
                return httpx2.Response(200, json={"payload": {"Orders": [dict(ORDER, AmazonOrderId="902-3")]}})
            return httpx2.Response(200, json={"payload": {"Orders": [ORDER], "NextToken": "n2"}}, headers={"x-amzn-RequestId": "req-1"})
        if path.startswith("/orders/v0/orders/") and path.endswith("/address"):
            return httpx2.Response(200, json={"payload": {"AmazonOrderId": path.split("/")[4], "ShippingAddress": {"Name": "N"}}})
        if path.startswith("/orders/v0/orders/") and path.count("/") == 4:
            return httpx2.Response(200, json={"payload": ORDER})
        if path == "/notifications/v1/destinations":
            return httpx2.Response(200, json={"payload": []})
        if path.startswith("/reports/2021-06-30/documents/"):
            return httpx2.Response(
                200, json={"reportDocumentId": "doc-1", "url": "https://s3.example/report.gz", "compressionAlgorithm": "GZIP"}
            )
        if path == "/report.gz":
            return httpx2.Response(200, content=gzip.compress(self.report_bytes))
        if path == "/feeds/2021-06-30/documents" and request.method == "POST":
            return httpx2.Response(201, json={"feedDocumentId": "fd-1", "url": "https://s3.example/upload"})
        if path == "/upload" and request.method == "PUT":
            return httpx2.Response(200)
        if path == "/feeds/2021-06-30/feeds" and request.method == "POST":
            return httpx2.Response(202, json={"feedId": "f-1"})
        return httpx2.Response(404, json={"errors": [{"code": "NotFound", "message": path}]}, headers={"x-amzn-RequestId": "req-404"})

    def by_path(self, fragment: str) -> list[httpx2.Request]:
        return [r for r in self.requests if fragment in r.url.path]
