import { describe, expect, it } from 'vitest';
import { emit, TASKS_SPEC } from './helpers.js';

describe('generateResources', () => {
  it('turns every operation into an Op literal and a typed method on the sync and async classes', async () => {
    const files = await emit(TASKS_SPEC, 'tasks', 'v1');
    const content = files['resources/tasks/v1.py'] ?? '';
    expect(content).not.toBe('');
    expect(content).toContain('from sdk.models.tasks import v1 as models');
    expect(content).toContain('class TasksV1(SyncResource):');
    expect(content).toContain('class AsyncTasksV1(AsyncResource):');
    for (const [pyName, opId] of [
      ['list_tasks', 'listTasks'],
      ['create_task', 'createTask'],
      ['get_task', 'getTask'],
      ['update_task', 'updateTask'],
      ['delete_task', 'deleteTask'],
    ]) {
      expect(content).toContain(`_op_${pyName} = Op(`);
      expect(content).toContain(`operation_id="${opId}"`);
      expect(content).toContain(`    def ${pyName}(`);
      expect(content).toContain(`    async def ${pyName}(`);
    }
    expect(content).toMatch(/def list_tasks\(\s*self,\s*\*,\s*after: str \| NotGiven = NOT_GIVEN,\s*limit: int \| NotGiven = NOT_GIVEN,\s*status: models\.TaskStatus \| NotGiven = NOT_GIVEN,/);
    expect(content).toMatch(/def create_task\(\s*self,\s*\*,\s*body: models\.CreateTaskInput \| Mapping\[str, Any\],/);
    expect(content).toMatch(/def update_task\(\s*self,\s*\*,\s*id: str,\s*body: models\.UpdateTaskInput \| Mapping\[str, Any\],/);
    expect(content).toMatch(/def get_task\([^)]*\) -> models\.Task:/);
    expect(content).toMatch(/def delete_task\([^)]*\) -> None:/);
    expect(content).toContain('method="DELETE"');
    expect(content).toContain('path="/tasks/{id}"');
    expect(content).toContain('__all__ = ["AsyncTasksV1", "TasksV1"]');
  });

  it('keeps the summary as the docstring and calls the runtime with a kwargs dict', async () => {
    const files = await emit(TASKS_SPEC, 'tasks', 'v1');
    const content = files['resources/tasks/v1.py'];
    expect(content).toContain('"""List tasks\n\n        GET /tasks\n        """');
    expect(content).toContain('return self._client.call(_op_get_task, {"id": id}, raw, paginate, request_options)');
    expect(content).toContain('return await self._client.call(_op_get_task, {"id": id}, raw, paginate, request_options)');
  });
});
