"""The reference smoke test over the tutorial's tasks API (``tests/fixtures/tasks-api.yml``).

``npm run smoke`` generates ``.build/tasks_sdk`` first, then runs this: the
printed query string must show ``status=done``, not ``status=TaskStatus.DONE``.
"""

from __future__ import annotations

import pathlib
import sys

import httpx2

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / ".build"))

from tasks_sdk import NotFoundError, TasksClient  # noqa: E402
from tasks_sdk.models.tasks import CreateTaskInput, TaskStatus  # noqa: E402

seen: list[tuple[str, str, str | None]] = []


def handler(request: httpx2.Request) -> httpx2.Response:
    seen.append((request.method, str(request.url), request.content.decode() or None))
    if request.url.path == "/tasks" and request.method == "GET":
        return httpx2.Response(200, json={"data": [{"id": "t-1", "title": "Ship it", "status": "done"}]})
    if request.url.path == "/tasks" and request.method == "POST":
        return httpx2.Response(201, json={"id": "t-2", "title": "Ship it", "status": "pending"})
    return httpx2.Response(404, json={"message": "no such task"})


client = TasksClient(base_url="https://api.tasks.example.com", transport=httpx2.MockTransport(handler))

page = client.tasks.list_tasks(status=TaskStatus.DONE, limit=10)
print("list:", [(t.id, t.status) for t in page.data])
created = client.tasks.create_task(CreateTaskInput(title="Ship it"))
print("created:", created.id, created.status)
try:
    client.tasks.get_task("missing")
except NotFoundError as exc:
    print("404:", exc)
print(*seen, sep="\n")

assert "status=done" in seen[0][1] and "limit=10" in seen[0][1], seen[0][1]
assert str(TaskStatus.DONE) == "done"
assert seen[1][2] == '{"title":"Ship it"}', seen[1][2]
print("ok")
