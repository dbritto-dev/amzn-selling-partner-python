import { describe, expect, it } from 'vitest';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateResources', () => {
  it('generates a sync and an async class per service with resolved method names', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['resources/tasks.py'] ?? '';
    expect(content).toContain('class TasksClient:');
    expect(content).toContain('class AsyncTasksClient:');
    expect(content).toContain('SERVICE = "tasks"');
    for (const name of ['list_tasks', 'create_task', 'get_task', 'update_task', 'delete_task']) {
      expect(content).toContain(`    def ${name}(`);
      expect(content).toContain(`    async def ${name}(`);
    }
    expect(content).toContain('from ..http_client import AsyncHttpClient, HttpClient, RequestOptions, path_segment');
    expect(content).toContain('from ..models import tasks');
  });

  it('builds parameters explicitly and calls the http client', async () => {
    const files = await emit(TASKS_SPEC);
    const content = files['resources/tasks.py'] ?? '';
    expect(content).toMatch(/def list_tasks\(\s*self,\s*\*,\s*after: str \| None = None,\s*limit: int \| None = None,\s*status: tasks\.TaskStatus \| str \| None = None,\s*request_options: RequestOptions \| None = None,\s*\) -> tasks\.TaskList:/);
    expect(content).toContain('params: dict[str, Any] = {"after": after, "limit": limit, "status": status}');
    expect(content).toContain('return self._client.request(\n            "GET",\n            "/tasks",\n            operation="listTasks",\n            service=SERVICE,\n            params=params,\n            response=tasks.TaskList,\n            options=request_options,\n        )');
    expect(content).toMatch(/def create_task\(\s*self,\s*\*,\s*body: tasks\.CreateTaskInput \| Mapping\[str, Any\],/);
    expect(content).toContain('json=body,');
    expect(content).toContain('f"/tasks/{path_segment(id)}"');
    expect(content).toMatch(/def delete_task\([^)]*\) -> None:/);
    expect(content).toContain('return await self._client.request(');
    expect(content).toContain('"""List tasks\n\n        GET /tasks\n        """');
  });

  it('writes the resources registry', async () => {
    const files = await emit(TASKS_SPEC);
    const init = files['resources/__init__.py'] ?? '';
    expect(init).toContain('"tasks": ("TasksClient", "AsyncTasksClient"),');
    expect(init).toContain('"tasks.listTasks": ("list_tasks", "GET", "/tasks", False, False),');
    expect(init).toContain('"tasks.deleteTask": ("delete_task", "DELETE", "/tasks/{id}", False, False),');
  });
});
