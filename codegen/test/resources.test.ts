import { describe, expect, it } from 'vitest';
import { emit, emitInline, TASKS_SPEC } from './helpers.js';

describe('generateResources', () => {
  it('generates a sync and an async class per service with resolved method names', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['resources/tasks.py'] ?? '';
    expect(content).toContain('class TasksResource:');
    expect(content).toContain('class AsyncTasksResource:');
    expect(content).toContain('    def __init__(self, http: HttpClient) -> None:\n        self._http = http');
    expect(content).toContain('    def __init__(self, http: AsyncHttpClient) -> None:');
    expect(content).toContain('SERVICE = "tasks"');
    for (const name of ['list_tasks', 'create_task', 'get_task', 'update_task', 'delete_task']) {
      expect(content).toContain(`    def ${name}(`);
      expect(content).toContain(`    async def ${name}(`);
    }
    expect(content).toContain('from .._http import AsyncHttpClient, HttpClient, RequestOptions, path_segment');
    expect(content).toContain('from ..models import tasks');
  });

  it('builds parameters explicitly and calls the http client', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['resources/tasks.py'] ?? '';
    expect(content).toMatch(/def list_tasks\(\s*self,\s*\*,\s*after: str \| None = None,\s*limit: int \| None = None,\s*status: tasks\.TaskStatus \| str \| None = None,\s*request_options: RequestOptions \| None = None,\s*\) -> tasks\.TaskList:/);
    expect(content).toContain('params: dict[str, Any] = {"after": after, "limit": limit, "status": status}');
    expect(content).toContain('return self._http.request(\n            "GET",\n            "/tasks",\n            operation="listTasks",\n            service=SERVICE,\n            params=params,\n            response=tasks.TaskList,\n            options=request_options,\n        )');
    // path params and the body are positional, optional parameters keyword-only
    expect(content).toMatch(/def create_task\(\s*self,\s*body: tasks\.CreateTaskInput \| Mapping\[str, Any\],\s*\*,\s*request_options/);
    expect(content).toMatch(/def update_task\(\s*self,\s*id: str,\s*body: tasks\.UpdateTaskInput \| Mapping\[str, Any\],\s*\*,/);
    expect(content).toContain('json=body,');
    expect(content).toContain('f"/tasks/{path_segment(id)}"');
    expect(content).toMatch(/def delete_task\([^)]*\) -> None:/);
    expect(content).toContain('return await self._http.request(');
    expect(content).toContain('"""List tasks\n\n        GET /tasks\n        """');
  });

  it('handles header params, delimited arrays and non-JSON bodies (method names from the resolver)', async () => {
    const files = await emitInline(`
openapi: "3.0.3"
info: { title: Files API, version: "1.0.0" }
servers: [{ url: https://files.example.com }]
paths:
  /files/{path}:
    put:
      operationId: uploadFile
      tags: [Files]
      parameters:
        - { name: path, in: path, required: true, schema: { type: string } }
        - { name: X-Owner, in: header, required: true, schema: { type: string } }
        - { name: tags, in: query, style: form, explode: false, schema: { type: array, items: { type: string } } }
        - { name: ids, in: query, style: pipeDelimited, schema: { type: array, items: { type: string } } }
      requestBody:
        required: true
        content:
          application/octet-stream:
            schema: { type: string, format: binary }
      responses:
        "204": {}
    post:
      operationId: uploadForm
      tags: [Files]
      parameters:
        - { name: path, in: path, required: true, schema: { type: string } }
      requestBody:
        content:
          multipart/form-data:
            schema: { type: object, properties: { file: { type: string, format: binary } } }
      responses:
        "204": {}
`);
    const content = files['resources/files.py'] ?? '';
    expect(content).toMatch(/def update_file\(\s*self,\s*path: str,\s*body: bytes,\s*x_owner: str,\s*\*,\s*tags: list\[str\] \| None = None,\s*ids: list\[str\] \| None = None,/);
    expect(content).toContain('params: dict[str, Any] = {"tags": joined(tags, ","), "ids": joined(ids, "|")}');
    expect(content).toContain('headers: dict[str, Any] = {"X-Owner": x_owner}');
    expect(content).toContain('content=body,');
    expect(content).toContain('f"/files/{path_segment(path)}"');
    expect(content).toMatch(/def create_file\(\s*self,\s*path: str,\s*body: Mapping\[str, Any\],/);
    expect(content).toContain('files=body,');
  });

  it('marks the pagination token keyword for bandit (a parameter name, not a secret)', async () => {
    const files = await emit(TASKS_SPEC);
    const petstore = Object.values(files).join('\n');
    // the tasks spec has no paginated operation; the marker is rendered by the iter_ helper
    expect(petstore).not.toContain('token_param=');
    const paged = await emitInline(`
openapi: "3.0.3"
info: { title: Paged API, version: "1.0.0" }
servers: [{ url: https://paged.example.com }]
components:
  schemas:
    Page:
      type: object
      required: [items]
      properties:
        items: { type: array, items: { type: string } }
        nextToken: { type: string }
paths:
  /things:
    get:
      operationId: listThings
      tags: [Things]
      parameters:
        - { name: nextToken, in: query, schema: { type: string } }
      responses:
        "200": { content: { application/json: { schema: { $ref: "#/components/schemas/Page" } } } }
`);
    expect(paged['resources/things.py']).toContain('token_param="next_token",  # nosec B106');
  });

  it('writes the resources registry', async () => {
    const files = await emit(TASKS_SPEC);
    const init = files['resources/__init__.py'] ?? '';
    expect(init).toContain('"tasks": ("TasksResource", "AsyncTasksResource"),');
    expect(init).toContain('"tasks.listTasks": ("list_tasks", "GET", "/tasks", False, False),');
    expect(init).toContain('"tasks.deleteTask": ("delete_task", "DELETE", "/tasks/{id}", False, False),');
  });
});
