"""Minimal ASGI app used by ``benchmarks/bench.py`` (run under uvicorn).

Routes mirror the ``tests/fixtures/petstore_oas31.json`` spec:
``GET /v1/pets/{id}`` returns one pet, ``GET /v1/pets?size=<bytes>`` returns
a ``PetList`` padded to roughly ``size`` bytes, ``POST /v1/pets`` echoes.
"""

from __future__ import annotations

import json
from typing import Any

_PET = {
    "id": 1,
    "name": "Rex",
    "tag": "dog",
    "status": "available",
    "tags": ["friendly", "brown"],
    "createdAt": "2020-01-01T00:00:00Z",
    "birthday": "2019-05-04",
    "metadata": {"breed": "lab", "vet": "Dr. Smith"},
    "owner": {"name": "Alice", "email": "alice@example.com"},
    "category": {"name": "dogs", "parent": {"name": "animals"}},
    "weight": 30.5,
}
_PET_BYTES = json.dumps(_PET).encode()
_LISTS: dict[int, bytes] = {}


def pet_list(size: int) -> bytes:
    body = _LISTS.get(size)
    if body is None:
        per = len(_PET_BYTES) + 1
        n = max(1, size // per)
        items = [dict(_PET, id=i) for i in range(n)]
        body = json.dumps({"items": items, "total": n}).encode()
        _LISTS[size] = body
    return body


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] != "http":
        return
    path: str = scope["path"]
    query = scope.get("query_string", b"").decode()
    status = 200
    if path.startswith("/v1/pets/"):
        body = _PET_BYTES
    elif path == "/v1/pets" and scope["method"] == "GET":
        size = 0
        for part in query.split("&"):
            if part.startswith("size="):
                size = int(part[5:])
        body = pet_list(size) if size else json.dumps({"items": [_PET], "total": 1}).encode()
    elif path == "/v1/pets":
        received = b""
        while True:
            message = await receive()
            received += message.get("body", b"")
            if not message.get("more_body"):
                break
        body = received or _PET_BYTES
        status = 201
    else:
        body = b'{"code":"NF","message":"not found"}'
        status = 404
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
